"""Team-lead live checks: logs in from .env (never prints values), runs chat turns over /ws/chat, prints frame counts, tool starts per name and reload artifacts, cancels proposals.
Usage: uv run --with httpx --with websockets python .claude/team/livecheck.py SLOT:prompt_key ... (same SLOT = same conversation). Edit PROMPTS per sprint; defaults to the haiku model."""
import asyncio, json, sys, re
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


async def post(path, cookie, csrf):
    async with httpx.AsyncClient(base_url=API) as c:
        r = await c.post(path, headers={"Cookie": cookie, "Origin": ORIGIN, "X-CSRF-Token": csrf})
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
    convs = {}
    for name in sys.argv[1:]:
        slot, key = name.split(":")
        frames, text = await turn(cookie, model, PROMPTS[key], convs.get(slot))
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
    for slot,cid in convs.items():
        code, body = await get(f"/api/conversations/{cid}", cookie)
        arts=[]
        for m in body.get("messages",[]):
            for a in (m.get("artifacts") or []): arts.append((m.get("seq"), m.get("role"), a.get("kind") or a.get("type")))
        top=body.get("artifacts")
        print(f"reload {slot}: {code} message artifacts={arts} top-level artifacts={[ (a.get('message_seq'), a.get('kind')) for a in top] if isinstance(top,list) else None}")


PROMPTS = {
    "fights": "What boss fights are in Warcraft Logs report BKNtypgnhrxXvj84? One short line per fight.",
    "dmg": "In report BKNtypgnhrxXvj84, who were the top 3 damage dealers on the last boss kill? Three lines, no chart.",
    "chart": "In report BKNtypgnhrxXvj84, make a bar chart of the top 5 damage dealers on the last boss kill. Keep the text to one line.",
    "simplechart": "Make a bar chart of these values and nothing else: Alpha 3, Beta 5, Gamma 2. One line of text.",
    "bogus": "What fights are in report aaaaaaaaaaaaaaaa? One line.",
}

if __name__ == "__main__":
    asyncio.run(main())
