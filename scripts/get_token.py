"""Run once on your own computer to get the two Instagram secrets.

    python scripts/get_token.py <app id> <app secret> <short-lived user token>

Prints IG_USER_ID and a long-lived IG_ACCESS_TOKEN for each Instagram account
linked to your Facebook Pages. Paste them into the repo's secrets; never commit them.
"""
import sys

import requests

GRAPH = "https://graph.facebook.com/v25.0"


def get(path, **params):
    data = requests.get(f"{GRAPH}/{path}", params=params, timeout=60).json()
    if "error" in data:
        sys.exit(f"Meta said: {data['error'].get('message')}")
    return data


app_id, app_secret, short_token = sys.argv[1:4]
long_user = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                client_secret=app_secret, fb_exchange_token=short_token)["access_token"]
pages = get("me/accounts", access_token=long_user,
            fields="name,access_token,instagram_business_account{id,username}")["data"]
found = False
for page in pages:
    ig = page.get("instagram_business_account")
    if not ig:
        continue
    found = True
    print(f"\nInstagram @{ig.get('username')} (via Facebook Page '{page['name']}')")
    print(f"IG_USER_ID      = {ig['id']}")
    print(f"IG_ACCESS_TOKEN = {page['access_token']}")
if not found:
    sys.exit("No Instagram professional account is linked to the Pages this token can see.")
