"""081 live pre-check (team-lead runs it; prints public game data only, never a token).

Run from the main checkout:  uv run --env-file .env python <this file> > <out>.json
Needs WCL_CLIENT_ID/WCL_CLIENT_SECRET; BLIZZARD_CLIENT_ID/BLIZZARD_CLIENT_SECRET optional.
"""

import asyncio
import json
import os

import httpx

from wcl_agent.client import wcl_client
from wcl_agent.client.queries import MENU_DISCOVERY

REPORT = "bjXfNc92d8CPGhvB"
REPORT_Q = """
query R($code: String!) { reportData { report(code: $code) {
  zone { id name }
  fights { id encounterID name difficulty kill startTime endTime }
  masterData { abilities { gameID name type } actors(type: "NPC") { id gameID name } }
} } }
""".strip()


def _walk(sections, out, depth=0):
    for s in sections or []:
        out.append({
            "depth": depth,
            "title": s.get("title"),
            "spell": (s.get("spell") or {}).get("id"),
            "text": s.get("body_text"),
        })
        _walk(s.get("sections"), out, depth + 1)


async def journal(names):
    cid, secret = os.getenv("BLIZZARD_CLIENT_ID"), os.getenv("BLIZZARD_CLIENT_SECRET")
    if not cid or not secret:
        return {"skipped": "no Blizzard credentials"}
    out = {}
    async with httpx.AsyncClient(timeout=20) as http:
        tok = (await http.post("https://oauth.battle.net/token", data={"grant_type": "client_credentials"},
                               auth=(cid, secret))).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        base = "https://us.api.blizzard.com/data/wow"
        for name in names:
            r = await http.get(f"{base}/search/journal-encounter", headers=h, params={
                "namespace": "static-us", "locale": "en_US", "name.en_US": name, "orderby": "id:desc"})
            results = (r.json().get("results") or []) if r.status_code == 200 else []
            if not results:
                out[name] = {"status": r.status_code, "found": False}
                continue
            jid = results[0]["data"]["id"]
            e = (await http.get(f"{base}/journal-encounter/{jid}", headers=h,
                                params={"namespace": "static-us", "locale": "en_US"})).json()
            rows = []
            _walk(e.get("sections"), rows)
            out[name] = {"journal_id": jid, "instance": (e.get("instance") or {}).get("name"),
                         "description": e.get("description"), "sections": rows}
    return out


async def main():
    c = wcl_client.get_async_client()
    zones = ((await c.query(MENU_DISCOVERY)).get("data") or {}).get("worldData", {}).get("zones") or []
    top = max((z.get("expansion") or {}).get("id") or 0 for z in zones)
    tier = [{"id": z["id"], "name": z["name"], "frozen": z.get("frozen"),
             "encounters": z.get("encounters")} for z in zones if (z.get("expansion") or {}).get("id") == top]
    rep = ((await c.query(REPORT_Q, {"code": REPORT})).get("data") or {}).get("reportData", {}).get("report")
    names = sorted({e["name"] for z in tier if not z["frozen"] for e in z["encounters"] or []})
    print(json.dumps({"tier_zones": tier, "report": rep, "journal": await journal(names)}, indent=1))
    await c.aclose()


asyncio.run(main())
