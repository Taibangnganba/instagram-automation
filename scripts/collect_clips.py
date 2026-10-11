"""Turn an OpenShorts output folder into queue entries.

Usage: collect_clips.py <work_dir> <openshorts_log> <url> <credit> <exit_code>

Copies the best finished clips to <work_dir>/upload/ under stable names (the
workflow uploads that folder to the "clips" release) and writes one
state/clips/<id>.json per clip. The source is always marked processed so a broken video
never blocks the list.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import sys

from common import load_clips, load_config, mark_processed, now, save_clip, set_output

CLIP_READY = re.compile(r"^CLIP_READY (\d+) (.+\.mp4)\s*$", re.M)


def build_caption(clip, credit, cfg):
    text = (clip.get("video_description_for_instagram")
            or clip.get("video_title_for_youtube_short") or "").strip()
    parts = [text]
    if credit and cfg["credit_line"]:
        parts.append(cfg["credit_line"].format(source=credit))
    if cfg["hashtags"]:
        parts.append(cfg["hashtags"].strip())
    # Instagram allows 2,200 characters.
    return "\n\n".join(p for p in parts if p)[:2200]


def collect(work_dir, log_text, url, credit, cfg):
    metas = glob.glob(os.path.join(work_dir, "*_metadata.json"))
    if not metas:
        return []
    with open(metas[0]) as f:
        shorts = json.load(f).get("shorts") or []
    # OpenShorts prints the finished (hooked + captioned) file for each clip.
    served = {int(i): name.strip() for i, name in CLIP_READY.findall(log_text)}
    source_id = hashlib.sha1(url.encode()).hexdigest()[:10]
    upload_dir = os.path.join(work_dir, "upload")
    os.makedirs(upload_dir, exist_ok=True)

    entries = []
    # shorts are ordered best-first by the model.
    for i, clip in enumerate(shorts):
        if len(entries) >= cfg["clips_per_video"]:
            break
        path = os.path.join(work_dir, served.get(i, ""))
        if i not in served or not os.path.isfile(path):
            continue
        asset = f"{source_id}_clip_{i + 1}.mp4"
        shutil.copyfile(path, os.path.join(upload_dir, asset))
        entries.append({
            "id": asset[:-4],
            "asset": asset,
            "caption": build_caption(clip, credit, cfg),
            "hook": clip.get("viral_hook_text", ""),
            "seconds": round(float(clip.get("end", 0)) - float(clip.get("start", 0)), 1),
            "source_url": url,
            "credit": credit,
            "status": "ready",
            "attempts": 0,
            "created_at": now(),
        })
    return entries


if __name__ == "__main__":
    work_dir, log_path, url, credit, exit_code = sys.argv[1:6]
    cfg = load_config()
    log_text = open(log_path, errors="replace").read() if os.path.exists(log_path) else ""
    entries = collect(work_dir, log_text, url, credit, cfg)

    known = {c["id"] for c in load_clips()}
    entries = [e for e in entries if e["id"] not in known]
    for entry in entries:
        save_clip(entry)

    note = f"{len(entries)} clips" if entries else f"no clips (clipper exit code {exit_code})"
    mark_processed(url, note)
    print(f"{url}: {note}")
    set_output(clips=len(entries))
