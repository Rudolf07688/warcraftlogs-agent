"""Team-lead live checks: logs in from .env (never prints values), runs chat turns over /ws/chat, prints frame counts, tool starts per name and reload artifacts, cancels proposals.
Usage: uv run --with httpx --with websockets python .claude/team/livecheck.py SLOT:prompt_key ... (same SLOT = same conversation). Edit PROMPTS per sprint; defaults to the haiku model.
Each turn is judged: PASS/FAIL against EXPECT (answers known from the stored report, never from a model), else ANSWERED or EMPTY. Exit 1 on any FAIL or EMPTY.
  livecheck.py --facts CODE   prints the stored fights of a report (from Postgres), to write EXPECT entries from."""
import asyncio, json, sys, re, subprocess
import httpx, websockets

ENV = {}
for line in open("/home/rudolf/dev/warcraftlogs-agent/.env"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        ENV[k.strip()] = v.strip().strip('"').strip("'")

API = "http://localhost:8000"
ORIGIN = ENV.get("SITE_URL", "http://localhost:5173").rstrip("/")


async def login():
    async with httpx.AsyncClient(base_url=API) as c:
        r = await c.post("/api/auth/login", headers={"Origin": ORIGIN},
                         json={"email": ENV["BOOTSTRAP_ADMIN_EMAIL"], "password": ENV["BOOTSTRAP_ADMIN_PASSWORD"]})
        r.raise_for_status()
        sc = r.headers.get_list("set-cookie")
        cookie = "; ".join(s.split(";", 1)[0] for s in sc)
        return cookie, r.json()["csrf_token"]


async def get(path, cookie):
    async with httpx.AsyncClient(base_url=API) as c:
        r = await c.get(path, headers={"Cookie": cookie, "Origin": ORIGIN})
        return r.status_code, r.json()


async def post(path, cookie, csrf, body=None):
    async with httpx.AsyncClient(base_url=API) as c:
        r = await c.post(path, headers={"Cookie": cookie, "Origin": ORIGIN, "X-CSRF-Token": csrf}, json=body)
        return r.status_code, r.json()


async def turn(cookie, model, content, conv=None, timeout=240):
    frames = []
    async with websockets.connect("ws://localhost:8000/ws/chat", origin=ORIGIN,
                                  additional_headers={"Cookie": cookie}, max_size=None) as ws:
        msg = {"model": model, "content": content}
        if conv:
            msg["conversation_id"] = conv
        await ws.send(json.dumps(msg))
        async def pump():
            while True:
                f = json.loads(await ws.recv())
                frames.append(f)
                if f.get("type") in ("done", "error"):
                    return
        await asyncio.wait_for(pump(), timeout)
    text = "".join(f.get("text") or f.get("token") or f.get("content") or "" for f in frames if f.get("type") == "token")
    return frames, text


async def main():
    cookie, csrf = await login()
    _, models = await get("/api/models", cookie)
    lst = models.get("models", models); ids=[m if isinstance(m,str) else (m.get("id") or m.get("name")) for m in lst]
    model = next((m for m in ids if "haiku" in m), ids[0]); print("using", model)
    convs, results = {}, []
    for name in sys.argv[1:]:
        slot, key = name.split(":")
        prompt = PROMPTS.get(key)
        if key == "kickoff":  # the welcome-page recent-raid click: investigate, then send its kickoff prompt
            _, rr = await get("/api/recent-raids", cookie)
            raids = rr.get("raids", [])
            raid = next((r for r in raids if r.get("difficulty") == 4), raids[0] if raids else None)
            if raid is None:
                print("kickoff: no recent raids"); continue
            code, inv = await post(f"/api/raids/{raid['report_code']}/investigate", cookie, csrf, {"model": model})
            print(f"kickoff: {raid['report_code']} difficulty={raid.get('difficulty')} investigate={code}")
            convs[slot], prompt = inv["conversation_id"], inv["kickoff_prompt"]
            await asyncio.sleep(20)  # let the background pre-fetch warm the store, as a user reading the page would
        frames, text = await turn(cookie, model, prompt, convs.get(slot))
        for f in frames:
            if f["type"]=="meta" and f.get("conversation_id"): convs[slot]=f["conversation_id"]
        types={}
        for f in frames: types[f["type"]]=types.get(f["type"],0)+1
        starts={}
        for f in frames:
            if f["type"]=="tool_start": starts[f.get("name")]=starts.get(f.get("name"),0)+1
        ends=[(f.get("name"), f.get("ok"), f.get("ms") or f.get("duration_ms")) for f in frames if f["type"]=="tool_end"]
        print(f"\n=== {name} conv={convs.get(slot)} ===\nframes: {types}\ntool_start per name: {starts}\ntool_end: {ends}")
        for f in frames:
            if f["type"] in ("error",): print("  ", f)
            if f["type"]=="proposal":
                pid=f["proposal"]["id"]; print("  proposal cancelled:", (await post(f"/api/profile/proposals/{pid}/cancel", cookie, csrf))[0])
        print("TEXT:", text[:700])
        results.append((name, judge(key, frames, text)))
        print("CHECK", *results[-1][1])
    for slot,cid in convs.items():
        code, body = await get(f"/api/conversations/{cid}", cookie)
        arts=[]
        for m in body.get("messages",[]):
            for a in (m.get("artifacts") or []): arts.append((m.get("seq"), m.get("role"), a.get("kind") or a.get("type")))
        top=body.get("artifacts")
        print(f"reload {slot}: {code} message artifacts={arts} top-level artifacts={[ (a.get('message_seq'), a.get('kind')) for a in top] if isinstance(top,list) else None}")
    tally = {}
    for _, (v, _why) in results: tally[v] = tally.get(v, 0) + 1
    print("\nLIVE RESULT:", ", ".join(f"{n} {v}" for v, n in sorted(tally.items())),
          "|", "; ".join(f"{n}={v}" for n, (v, _w) in results))
    return 1 if tally.get("FAIL") or tally.get("EMPTY") else 0


def judge(key, frames, text):
    """PASS/FAIL against EXPECT, else ANSWERED/EMPTY. Checks the answer text plus any
    artifact/chart frames, not tool frames (a fight list there names every boss)."""
    if any(f.get("type") == "error" for f in frames) or not text.strip():
        return "EMPTY", "no answer text" if not any(f.get("type") == "error" for f in frames) else "error frame"
    exp = EXPECT.get(key)
    if not exp:
        return "ANSWERED", "no EXPECT entry"
    skip = {"token", "tool_start", "tool_end", "meta", "done", "status", "thinking"}
    hay = text + " " + json.dumps([f for f in frames if f.get("type") not in skip])
    missing = [r for r in exp.get("all", []) if not re.search(r, hay, re.I)]
    wrong = [r for r in exp.get("none", []) if re.search(r, text, re.I)]
    if missing or wrong:
        return "FAIL", f"missing {missing} wrong {wrong}".strip()
    return "PASS", exp.get("why", "")


def facts(code):
    """The stored fights of a report, read inside the db container (no secrets printed)."""
    sql = ("select payload->'data'->'reportData'->'report'->'fights' from raw_fetches "
           f"where report_code='{re.sub(r'[^A-Za-z0-9]', '', code)}' and operation_name='ReportSummary' "
           "order by fetched_at desc limit 1")
    out = subprocess.run(["docker", "exec", "warcraftlogs-agent-db-1", "sh", "-c",
                          f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "{sql}"'],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        print(f"no stored ReportSummary for {code}"); return
    fights = json.loads(out)
    for f in fights:
        print(f"{f['id']:3} {f.get('name')!s:40} kill={f.get('kill')} difficulty={f.get('difficulty')} encounter={f.get('encounterID')}")
    kills = [f for f in fights if f.get("kill") and f.get("encounterID")]
    if kills:
        k = kills[-1]
        print(f"last boss kill: fight {k['id']} {k['name']} (difficulty {k.get('difficulty')})")


PROMPTS = {
    # sprint 2026-11-01b: big-report turns (046/048), clean-up (047/049). "kickoff" is built in above.
    "chart5": "In report BKNtypgnhrxXvj84, make a bar chart of the top 5 damage dealers on the last boss kill. Keep the text to one line that names the boss.",
    # sprint 2026-11-01: knowledge base (043/044/045)
    "stored": "Which fights are stored for report BKNtypgnhrxXvj84? Use only data we already have stored; one short line per fight.",
    "guide": "From our class guides only (search the knowledge base), how should an arms warr open? Two lines.",
    "topdmg": "In report BKNtypgnhrxXvj84, who were the top 3 damage dealers on the last boss kill? Three lines, no chart.",
    "hi": "hi",
    "fmage": "From our class guides only (search the knowledge base), what should a frost mage prioritise in single target? Two lines.",
    "related": "From what we already have stored, who topped damage on the Ula'tek heroic kill? One line.",
    "fightsq": "What boss fights are in report BKNtypgnhrxXvj84? Count them only, one line.",
    "secret": "Remember this for later: our raid's codeword for the next pull is PURPLE-OTTER-42. Just say ok.",
    "recall": "Search our past conversations: what was the raid codeword for the next pull? One line.",
}

# Expected answers: regexes on the answer ("all" may also match a chart/artifact frame).
# BKNtypgnhrxXvj84 (--facts): fights 1-2 are timed M+ keys; the last boss kill is fight 32,
# Ula'tek heroic. sc-365 ("Agent picks the wrong last boss kill") is caught here.
LAST_KILL = {"all": [r"ula.?tek"], "none": [r"nalorakk", r"blinding vale", r"kith.?ix"],
             "why": "last boss kill = Ula'tek heroic (fight 32)"}
EXPECT = {
    "topdmg": LAST_KILL,
    "chart5": LAST_KILL,
    "related": {"all": [r"\w"], "none": [r"kith.?ix"], "why": "answers about Ula'tek, not Kith'ix"},
    "recall": {"all": [r"PURPLE-OTTER-42"], "why": "recalls the codeword"},
}

if __name__ == "__main__":
    if sys.argv[1:2] == ["--facts"]:
        facts(sys.argv[2])
    else:
        sys.exit(asyncio.run(main()))
