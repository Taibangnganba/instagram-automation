import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_ROOT", str(tmp_path))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    (tmp_path / "state" / "clips").mkdir(parents=True)
    (tmp_path / "config.yml").write_text(
        'clips_per_video: 2\nmin_ready_clips: 2\nhashtags: "#funny"\n'
        'credit_line: "🎥 {source}"\nmax_attempts: 2\n')
    (tmp_path / "sources.txt").write_text(
        "# comment\nhttps://a.example/1 | @one\n\nhttps://a.example/2\n")
    mods = {}
    for name in ("common", "ig", "next_source", "collect_clips", "post_reel", "discover"):
        sys.modules.pop(name, None)
    for name in ("common", "ig", "next_source", "collect_clips", "post_reel", "discover"):
        mods[name] = importlib.import_module(name)
    mods["root"] = tmp_path
    return mods


def fake_openshorts_run(root, n=3):
    work = root / "work"
    work.mkdir()
    shorts = [{"start": 10.0 * i, "end": 10.0 * i + 30,
               "video_description_for_instagram": f"Funny moment {i}",
               "viral_hook_text": f"Hook {i}"} for i in range(n)]
    (work / "Title_metadata.json").write_text(json.dumps({"shorts": shorts}))
    log = ""
    for i in range(n):
        if i == 1:
            continue  # clip 2 failed to render
        name = f"subtitled_1_hooked_1_Title_clip_{i + 1}.mp4"
        (work / name).write_bytes(b"video%d" % i)
        log += f"   ✅ Clip {i + 1} ready\nCLIP_READY {i} {name}\n"
    return work, log


def test_sources_and_next(repo):
    assert repo["common"].load_sources() == [("https://a.example/1", "@one"), ("https://a.example/2", "")]
    source, _ = repo["next_source"].pick()
    assert source == ("https://a.example/1", "@one")
    repo["common"].mark_processed("https://a.example/1", "x")
    assert repo["next_source"].pick()[0] == ("https://a.example/2", "")
    repo["common"].mark_processed("https://a.example/2", "x")
    assert repo["next_source"].pick()[0] is None


def test_collect_skips_failed_and_caps(repo):
    work, log = fake_openshorts_run(repo["root"], n=4)
    cfg = repo["common"].load_config()
    entries = repo["collect_clips"].collect(str(work), log, "https://a.example/1", "@one", cfg)
    assert [e["id"].split("_clip_")[1] for e in entries] == ["1", "3"]  # 2 failed, capped at 2
    assert entries[0]["caption"] == "Funny moment 0\n\n🎥 @one\n\n#funny"
    assert (work / "upload" / entries[1]["asset"]).read_bytes() == b"video2"
    assert entries[0]["seconds"] == 30.0


def test_no_more_clips_when_queue_full(repo):
    work, log = fake_openshorts_run(repo["root"])
    cfg = repo["common"].load_config()
    for e in repo["collect_clips"].collect(str(work), log, "u", "", cfg):
        repo["common"].save_clip(e)
    source, reason = repo["next_source"].pick()
    assert source is None and "already waiting" in reason


class FakeResp:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


class FakeHTTP:
    """Imitates the Graph API. resumable=False rejects direct upload."""

    def __init__(self, resumable=True, fail_publish=False):
        self.calls, self.resumable, self.fail_publish, self.polls = [], resumable, fail_publish, 0

    def request(self, method, url, params=None, **kw):
        self.calls.append((method, url.split("/v25.0/")[1], dict(params)))
        assert params["access_token"] == "TOKEN"
        if url.endswith("/IGID/media"):
            assert params["media_type"] == "REELS"
            if params.get("upload_type") == "resumable" and not self.resumable:
                return FakeResp(400, {"error": {"message": "resumable not allowed", "code": 100}})
            return FakeResp(200, {"id": "C1"})
        if url.endswith("/C1"):
            self.polls += 1
            return FakeResp(200, {"status_code": "IN_PROGRESS" if self.polls < 3 else "FINISHED"})
        if url.endswith("/media_publish"):
            assert params["creation_id"] == "C1"
            if self.fail_publish:
                return FakeResp(400, {"error": {"message": "nope", "code": 9}})
            return FakeResp(200, {"id": "M1"})
        if url.endswith("/M1"):
            return FakeResp(200, {"permalink": "https://www.instagram.com/reel/abc/"})
        raise AssertionError(url)

    def post(self, url, headers=None, data=None, **kw):
        body = data.read()
        self.calls.append(("UPLOAD", url, headers))
        assert headers["Authorization"] == "OAuth TOKEN"
        assert headers["file_size"] == str(len(body)) and headers["offset"] == "0"
        return FakeResp(200, {"success": True})


def queue_one(repo):
    work, log = fake_openshorts_run(repo["root"])
    cfg = repo["common"].load_config()
    entries = repo["collect_clips"].collect(str(work), log, "u", "@one", cfg)
    for e in entries:
        repo["common"].save_clip(e)
    return str(work / "upload" / entries[0]["asset"]), entries


def test_post_direct_upload(repo):
    path, entries = queue_one(repo)
    http = FakeHTTP()
    client = repo["ig"].Instagram("IGID", "TOKEN", session=http, sleep=lambda s: None)
    assert repo["post_reel"].post(path, client) == 0
    clips = {c["id"]: c for c in repo["common"].load_clips()}
    first = clips[entries[0]["id"]]
    assert first["status"] == "posted" and first["permalink"].endswith("/abc/")
    assert clips[entries[1]["id"]]["status"] == "ready"
    assert any(c[0] == "UPLOAD" and "rupload.facebook.com/ig-api-upload/v25.0/C1" in c[1] for c in http.calls)
    assert repo["post_reel"].next_clip()["id"] == entries[1]["id"]


def test_post_falls_back_to_public_url(repo, monkeypatch):
    path, entries = queue_one(repo)
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    monkeypatch.setenv("REPO_IS_PUBLIC", "true")
    http = FakeHTTP(resumable=False)
    client = repo["ig"].Instagram("IGID", "TOKEN", session=http, sleep=lambda s: None)
    assert repo["post_reel"].post(path, client) == 0
    creates = [c for c in http.calls if c[1] == "IGID/media"]
    assert creates[1][2]["video_url"] == f"https://github.com/me/repo/releases/download/clips/{entries[0]['asset']}"


def test_failed_post_retries_then_gives_up(repo):
    path, entries = queue_one(repo)
    for expected in ("ready", "failed"):  # max_attempts: 2
        client = repo["ig"].Instagram("IGID", "TOKEN", session=FakeHTTP(fail_publish=True), sleep=lambda s: None)
        assert repo["post_reel"].post(path, client) == 1
        clip = [c for c in repo["common"].load_clips() if c["id"] == entries[0]["id"]][0]
        assert clip["status"] == expected and "nope" in clip["last_error"]
    assert repo["post_reel"].next_clip()["id"] == entries[1]["id"]


def test_dry_run_changes_nothing(repo, monkeypatch):
    path, entries = queue_one(repo)
    monkeypatch.setenv("DRY_RUN", "1")
    assert repo["post_reel"].post(path) == 0
    assert all(c["status"] == "ready" and c["attempts"] == 0 for c in repo["common"].load_clips())


FEED_XML = """<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <entry><yt:videoId>{0}3</yt:videoId><link rel="alternate" href="https://www.youtube.com/shorts/{0}3"/></entry>
 <entry><yt:videoId>{0}2</yt:videoId><link rel="alternate" href="https://www.youtube.com/watch?v={0}2"/></entry>
 <entry><yt:videoId>{0}1</yt:videoId><link rel="alternate" href="https://www.youtube.com/watch?v={0}1"/></entry>
</feed>"""
ID_A, ID_B = "UC" + "a" * 22, "UC" + "b" * 22


def test_discover_round_robin_skips_shorts_and_seen(repo):
    (repo["root"] / "sources.txt").write_text("")
    (repo["root"] / "channels.txt").write_text(
        f"# c\nhttps://www.youtube.com/@alpha | @alpha\n{ID_B}\nhttps://www.youtube.com/@broken\n")
    repo["common"].mark_processed("https://www.youtube.com/watch?v=A2", "done")

    def fetch(url):
        if url.endswith("/@alpha"):
            return f'<link rel="alternate" href="https://www.youtube.com/feeds/videos.xml?channel_id={ID_A}">'
        if url.endswith("/@broken"):
            return "<html>consent</html>"
        return FEED_XML.format("A" if ID_A in url else "B")

    got = repo["discover"].discover(fetch, 3)
    assert got == [("https://www.youtube.com/watch?v=A1", "@alpha"),
                   ("https://www.youtube.com/watch?v=B2", ID_B),
                   ("https://www.youtube.com/watch?v=B1", ID_B)]
