"""Minimal Instagram Graph API client for publishing Reels (official API)."""
import os
import time

import requests

API_VERSION = os.environ.get("IG_API_VERSION", "v25.0")
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}"


class IGError(RuntimeError):
    pass


class Instagram:
    def __init__(self, ig_user_id, token, session=None, sleep=time.sleep):
        self.ig_user_id = ig_user_id
        self.token = token
        self.http = session or requests.Session()
        self.sleep = sleep

    def _call(self, method, url, **kwargs):
        params = kwargs.pop("params", {})
        params["access_token"] = self.token
        resp = self.http.request(method, url, params=params, timeout=120, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            raise IGError(f"HTTP {resp.status_code}: non-JSON response")
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise IGError(f"HTTP {resp.status_code}: {err.get('message', data)} "
                          f"(code {err.get('code')}, subcode {err.get('error_subcode')})")
        return data

    def account(self):
        return self._call("GET", f"{GRAPH}/{self.ig_user_id}",
                          params={"fields": "username,followers_count,media_count"})

    def publishing_quota(self):
        data = self._call("GET", f"{GRAPH}/{self.ig_user_id}/content_publishing_limit",
                          params={"fields": "quota_usage,config"})
        return (data.get("data") or [{}])[0]

    def create_reel_container(self, caption, video_url=None):
        params = {"media_type": "REELS", "caption": caption, "share_to_feed": "true"}
        if video_url:
            params["video_url"] = video_url
        else:
            params["upload_type"] = "resumable"
        return self._call("POST", f"{GRAPH}/{self.ig_user_id}/media", params=params)["id"]

    def upload_file(self, container_id, path):
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            resp = self.http.post(
                f"{RUPLOAD}/{container_id}",
                headers={"Authorization": f"OAuth {self.token}",
                         "offset": "0", "file_size": str(size)},
                data=f, timeout=900)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or not data.get("success"):
            raise IGError(f"upload failed: HTTP {resp.status_code} {data or resp.text[:300]}")

    def wait_until_ready(self, container_id, timeout=600, interval=20):
        waited = 0
        while True:
            data = self._call("GET", f"{GRAPH}/{container_id}",
                              params={"fields": "status_code,status"})
            code = data.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"Instagram rejected the video: {data.get('status', code)}")
            if waited >= timeout:
                raise IGError(f"video still processing after {timeout}s (status {code})")
            self.sleep(interval)
            waited += interval

    def publish(self, container_id):
        media_id = self._call("POST", f"{GRAPH}/{self.ig_user_id}/media_publish",
                              params={"creation_id": container_id})["id"]
        try:  # the reel is live at this point; a failed lookup must not cause a re-post
            link = self._call("GET", f"{GRAPH}/{media_id}", params={"fields": "permalink"})
        except IGError:
            link = {}
        return media_id, link.get("permalink", "")

    def post_reel(self, path, caption, public_url=None):
        """Upload the file directly; if Meta refuses direct upload for this app,
        fall back to letting Instagram fetch it from a public URL."""
        try:
            container = self.create_reel_container(caption)
            self.upload_file(container, path)
        except IGError as first:
            if not public_url:
                raise
            print(f"Direct upload unavailable ({first}); using public URL instead.")
            container = self.create_reel_container(caption, video_url=public_url)
        self.wait_until_ready(container)
        return self.publish(container)
