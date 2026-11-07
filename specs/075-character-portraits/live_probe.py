"""075 live pre-check (team-lead runs it): prints the character-media response SHAPE for one
character. Never prints the token or the secret. Usage, from the repo root with .env loaded:

    uv run python specs/075-character-portraits/live_probe.py eu tarren-mill somename
"""

import os
import sys
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()
region, realm, name = sys.argv[1:4]
tok = httpx.post(
    "https://oauth.battle.net/token",
    data={"grant_type": "client_credentials"},
    auth=(os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"]),
    timeout=10,
)
print("token status", tok.status_code, "keys", sorted(tok.json()))
url = (
    f"https://{region}.api.blizzard.com/profile/wow/character/"
    f"{quote(realm, safe='')}/{quote(name.lower(), safe='')}/character-media"
)
r = httpx.get(
    url,
    params={"namespace": f"profile-{region}", "locale": "en_US"},
    headers={"Authorization": f"Bearer {tok.json()['access_token']}"},
    timeout=10,
)
print("media status", r.status_code, "redirect", r.headers.get("location"))
body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
print("top keys", sorted(body))
for a in body.get("assets", []):
    print("asset", a.get("key"), a.get("value"))
missing = httpx.get(
    f"https://{region}.api.blizzard.com/profile/wow/character/{quote(realm, safe='')}/zzzqxnotreal/character-media",
    params={"namespace": f"profile-{region}", "locale": "en_US"},
    headers={"Authorization": f"Bearer {tok.json()['access_token']}"},
    timeout=10,
)
print("unknown character status", missing.status_code)
