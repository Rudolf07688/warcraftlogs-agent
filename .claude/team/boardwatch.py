"""Board milestone filter for a Monitor: tail -n0 -F .git/team-board/<board>.jsonl | python3 -u .claude/team/boardwatch.py"""
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
    except Exception:
        continue
    t = e.get("text", "")
    if e.get("kind") in ("handoff", "merge", "escalation") or t.startswith(("ESCALATION", "SPAWN-REQUEST", "STOP-REQUEST")):
        print("#%s %s %s: %s" % (e.get("id"), e.get("author"), str(e.get("kind")).upper(), t[:220]), flush=True)
