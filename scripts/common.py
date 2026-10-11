"""Shared helpers: config, source list and the clip queue."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).resolve().parent.parent))
CONFIG = ROOT / "config.yml"
SOURCES = ROOT / "sources.txt"
CLIPS = ROOT / "state" / "clips"
PROCESSED = ROOT / "state" / "processed.txt"

DEFAULTS = {
    "clips_per_video": 4,
    "min_ready_clips": 6,
    "max_source_minutes": 30,
    "auto_hook": True,
    "hashtags": "",
    "credit_line": "",
    "max_attempts": 3,
    "videos_per_discovery": 2,
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config():
    data = yaml.safe_load(CONFIG.read_text()) if CONFIG.exists() else {}
    return {**DEFAULTS, **(data or {})}


def load_sources():
    """Return [(url, credit)] in file order, ignoring comments and blanks."""
    out = []
    if not SOURCES.exists():
        return out
    for line in SOURCES.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, credit = line.partition("|")
        out.append((url.strip(), credit.strip()))
    return out


def load_processed():
    if not PROCESSED.exists():
        return set()
    return {l.split("\t")[0].strip() for l in PROCESSED.read_text().splitlines() if l.strip()}


def mark_processed(url, note):
    with PROCESSED.open("a") as f:
        f.write(f"{url}\t{now()}\t{note}\n")


def load_clips():
    """All clips, oldest first. One JSON file per clip so that the two
    workflows never edit the same file and commits cannot conflict."""
    clips = [json.loads(p.read_text()) for p in CLIPS.glob("*.json")]
    return sorted(clips, key=lambda c: (c["created_at"], c["id"]))


def save_clip(clip):
    CLIPS.mkdir(parents=True, exist_ok=True)
    (CLIPS / f"{clip['id']}.json").write_text(
        json.dumps(clip, indent=2, ensure_ascii=False) + "\n")


def ready_clips():
    return [c for c in load_clips() if c["status"] == "ready"]


def set_output(**values):
    """Expose values to later GitHub Actions steps (and print them locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    for key, value in values.items():
        print(f"{key}={value}")
        if path:
            with open(path, "a") as f:
                f.write(f"{key}={value}\n")
