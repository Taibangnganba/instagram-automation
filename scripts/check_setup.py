"""Confirm the Instagram secrets work, without posting anything."""
import os
import sys

from common import load_sources, load_processed, ready_clips
from ig import IGError, Instagram

missing = [k for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "GEMINI_API_KEY") if not os.environ.get(k)]
if missing:
    print(f"::error::Missing repository secrets: {', '.join(missing)}")
    sys.exit(1)

try:
    ig = Instagram(os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"])
    acct = ig.account()
    quota = ig.publishing_quota()
except IGError as e:
    print(f"::error::Instagram rejected the token or account id: {e}")
    sys.exit(1)

print(f"Connected to @{acct.get('username')} "
      f"({acct.get('followers_count')} followers, {acct.get('media_count')} posts)")
print(f"API posts used in the last 24h: {quota.get('quota_usage')}")
pending = [u for u, _ in load_sources() if u not in load_processed()]
print(f"Sources waiting: {len(pending)} | Clips ready to post: {len(ready_clips())}")
