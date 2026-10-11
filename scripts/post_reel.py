"""Publish the next ready clip to Instagram and record the result.

Usage: post_reel.py pick              -> prints the asset to download
       post_reel.py post <video path> -> publishes it
Set DRY_RUN=1 to go through the motions without posting.
"""
import os
import sys

from common import load_config, now, ready_clips, save_clip, set_output
from ig import IGError, Instagram


def next_clip():
    ready = ready_clips()
    return ready[0] if ready else None


def public_url(asset):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or os.environ.get("REPO_IS_PUBLIC") != "true":
        return None
    return f"https://github.com/{repo}/releases/download/clips/{asset}"


def post(path, client=None):
    cfg = load_config()
    clip = next_clip()
    if not clip:
        print("Nothing to post.")
        return 0
    if os.environ.get("DRY_RUN") == "1":
        print(f"DRY RUN - would post {clip['asset']} ({os.path.getsize(path)} bytes):\n{clip['caption']}")
        return 0

    client = client or Instagram(os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"])
    clip["attempts"] += 1
    try:
        media_id, permalink = client.post_reel(path, clip["caption"], public_url(clip["asset"]))
    except IGError as e:
        clip["last_error"] = str(e)
        if clip["attempts"] >= cfg["max_attempts"]:
            clip["status"] = "failed"
        save_clip(clip)
        print(f"::error::Posting {clip['id']} failed (attempt {clip['attempts']}): {e}")
        return 1
    clip.update(status="posted", posted_at=now(), media_id=media_id, permalink=permalink)
    clip.pop("last_error", None)
    save_clip(clip)
    print(f"Posted {clip['id']}: {permalink}")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "pick":
        clip = next_clip()
        if clip:
            set_output(run="true", asset=clip["asset"])
        else:
            print("Queue is empty - nothing to post.")
            set_output(run="false")
    else:
        sys.exit(post(sys.argv[2]))
