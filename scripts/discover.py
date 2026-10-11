"""Find new videos on the channels in channels.txt and add them to sources.txt.

Runs only when the pipeline is about to run dry: no unprocessed links left in
sources.txt and fewer clips waiting than min_ready_clips. Uses YouTube's public
channel feeds, so no API key is needed.
"""
import re
import sys
import xml.etree.ElementTree as ET

import requests

from common import ROOT, SOURCES, load_config, load_processed, load_sources, ready_clips

CHANNELS = ROOT / "channels.txt"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def load_channels():
    out = []
    if not CHANNELS.exists():
        return out
    for line in CHANNELS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ref, _, credit = line.partition("|")
        out.append((ref.strip(), credit.strip()))
    return out


def channel_id(ref, fetch):
    """Accept a UC... id, a /channel/UC... link, or an @handle link."""
    m = re.search(r"(UC[\w-]{22})", ref)
    if m:
        return m.group(1)
    url = ref if ref.startswith("http") else f"https://www.youtube.com/{ref if ref.startswith('@') else '@' + ref}"
    html = fetch(url)
    m = (re.search(r'channel_id=(UC[\w-]{22})', html)
         or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', html)
         or re.search(r'/channel/(UC[\w-]{22})', html))
    if not m:
        raise ValueError(f"could not find the channel ID for {ref}; put the UC... ID in channels.txt instead")
    return m.group(1)


def parse_feed(xml_text):
    """Newest-first list of long-form video URLs (Shorts are skipped)."""
    urls = []
    for entry in ET.fromstring(xml_text).findall("a:entry", NS):
        vid = entry.findtext("yt:videoId", namespaces=NS)
        link = entry.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        if vid and "/shorts/" not in href:
            urls.append(f"https://www.youtube.com/watch?v={vid}")
    return urls


def discover(fetch, limit):
    """Up to `limit` unseen videos, taking turns between channels."""
    seen = load_processed() | {u for u, _ in load_sources()}
    per_channel = []
    for ref, credit in load_channels():
        try:
            urls = parse_feed(fetch(FEED.format(channel_id(ref, fetch))))
        except Exception as e:  # one bad channel must not stop the others
            print(f"::warning::Skipping channel {ref}: {e}")
            continue
        per_channel.append([(u, credit or ref) for u in urls if u not in seen])
    picked = []
    while len(picked) < limit and any(per_channel):
        for videos in per_channel:
            if videos and len(picked) < limit:
                picked.append(videos.pop(0))
    return picked


def http_fetch(url):
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return resp.text


if __name__ == "__main__":
    cfg = load_config()
    pending = [u for u, _ in load_sources() if u not in load_processed()]
    if pending or len(ready_clips()) >= cfg["min_ready_clips"]:
        print("No new videos needed right now.")
        sys.exit(0)
    if not load_channels():
        print("channels.txt is empty - nothing to discover.")
        sys.exit(0)
    found = discover(http_fetch, cfg["videos_per_discovery"])
    with SOURCES.open("a") as f:
        for url, credit in found:
            f.write(f"{url} | {credit}\n")
            print(f"Added {url} ({credit})")
    if not found:
        print("::warning::No new videos on any channel in channels.txt.")
