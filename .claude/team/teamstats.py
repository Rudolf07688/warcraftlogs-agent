#!/usr/bin/env python3
"""Sprint facts as metrics for the "Agent Team: Improvement" dashboard.

Reads what each sprint's wrap-up already leaves on disk and pushes one gauge sample per
fact, timestamped at the sprint's end, to Alloy (OTLP/HTTP JSON), so Mimir holds the team's
history next to the live Claude Code metrics:

  meta/team-optimisation.md     baseline table: points, weighted cost, cost per point, shares
  meta/sprints/<sprint>/usage.txt   per-agent calls and tokens (usage.py output)
  meta/sprints/<sprint>/board.jsonl team board: questions and their wait, rework, blockers

  uv run python .claude/team/teamstats.py                 # push every sprint
  uv run python .claude/team/teamstats.py --dry-run       # print the facts only
  uv run python .claude/team/teamstats.py --meta /path/to/meta

Run it at every wrap-up after the baseline row is written. Pushing again is safe while the
numbers are unchanged (same timestamp, same value). Mimir accepts samples up to its
out_of_order_time_window (observability/mimir/mimir.yaml) in the past.

Board rules: a question is "blocking" unless its key starts with live-check: or skill:
(those are queued for the lead's end pass by design). It is answered by the first later
entry from someone else with the same key, or by an answer that supersedes it. A rework
round is a hand-off whose text says rework or follow-up (tier L gate hand-offs don't count).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEIGHTS = {"cr": 0.1, "cc": 1.25, "out": 5.0, "inp": 1.0}  # cache read, cache write, output, input
QUEUED_KEYS = ("live-check:", "skill:")
REWORK = re.compile(r"\brework\b|\bfollow-up\b", re.IGNORECASE)


def role_of(agent: str) -> str:
    a = agent.lower()
    if a.startswith("main"):
        return "lead"
    if "product-owner" in a or "maren" in a:
        return "product owner"
    if "scrum" in a or "ilse" in a:
        return "scrum master"
    if "shortcut" in a:
        return "board admin"
    if "fix" in a and ("qa" in a or "p7" in a):
        return "QA fixes"
    if a.startswith(("qa", "p7")) or "security review" in a or "recheck" in a:
        return "QA"
    if "architecture docs" in a or "tomas" in a:
        return "docs"
    if "probe" in a:
        return "other"
    return "developers"


def parse_baseline(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text().splitlines():
        m = re.match(r"\|\s*(20\d\d-\d\d-\d\d\w?)\s*\|(.*)", line)
        if not m:
            continue
        cells = [c.strip().strip("*").strip() for c in m.group(2).split("|")]
        try:
            rows[m.group(1)] = {
                "points": float(cells[0]),
                "calls": float(cells[1]),
                "cost": float(cells[3]),
                "cost_per_point": float(cells[4]),
                "coordination": float(cells[5].rstrip("%")) / 100,
                "build": float(cells[6].rstrip("%")) / 100,
                "qa": float(cells[7].rstrip("%")) / 100,
            }
        except (IndexError, ValueError):
            continue
    return rows


def parse_usage(path: Path) -> list[dict]:
    agents = []
    for line in path.read_text().splitlines():
        if line.startswith(("agent ", "TOTAL")) or not line.strip():
            if line.startswith("TOTAL"):
                break
            continue
        m = re.match(r"(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", line)
        if not m:
            continue
        name = m.group(1).strip()
        calls, out, cr, cc = (int(m.group(i)) for i in range(2, 6))
        agents.append({"agent": name, "role": role_of(name), "calls": calls,
                       "context_per_call": (cr + cc) / calls if calls else 0.0,
                       "cost": (cr * WEIGHTS["cr"] + cc * WEIGHTS["cc"] + out * WEIGHTS["out"]) / 1e6})
    return agents


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def parse_board(path: Path) -> dict:
    ev = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    waits, unanswered = [], 0
    for q in ev:
        if q["kind"] != "question" or (q.get("key") or "").startswith(QUEUED_KEYS):
            continue
        answer = next((e for e in ev if e["id"] > q["id"] and (
            (e["kind"] == "answer" and e.get("supersedes") == q["id"])
            or (q.get("key") and e.get("key") == q["key"] and e["author"] != q["author"]
                and e["kind"] in ("answer", "decision", "change", "notice")))), None)
        if answer is None:
            unanswered += 1
        else:
            waits.append((ts(answer["ts"]) - ts(q["ts"])).total_seconds() / 60)
    start, end = ts(ev[0]["ts"]), ts(ev[-1]["ts"])
    return {
        "end": end,
        "duration_minutes": (end - start).total_seconds() / 60,
        "questions": len(waits) + unanswered,
        "questions_unanswered": unanswered,
        "question_wait_max_minutes": max(waits) if waits else 0.0,
        "question_wait_median_minutes": statistics.median(waits) if waits else 0.0,
        "rework_rounds": sum(1 for e in ev if e["kind"] == "handoff" and REWORK.search(e["text"])),
        "blockers": sum(1 for e in ev if e["kind"] == "blocker"),
        "board_entries": len(ev),
    }


def collect(meta: Path) -> list[dict]:
    baseline = parse_baseline(meta / "team-optimisation.md")
    sprints = []
    for d in sorted(p for p in (meta / "sprints").iterdir() if p.is_dir()):
        s = {"sprint": d.name, "facts": {}, "agents": []}
        if d.name in baseline:
            s["facts"].update(baseline[d.name])
        if (d / "board.jsonl").exists():
            b = parse_board(d / "board.jsonl")
            s["end"] = b.pop("end")
            s["facts"].update(b)
            if s["facts"].get("points"):
                s["facts"]["minutes_per_point"] = b["duration_minutes"] / s["facts"]["points"]
        else:
            # No board export (the first sprints): mark the end at 17:00 UTC on the sprint date.
            s["end"] = datetime.fromisoformat(d.name[:10] + "T17:00:00+00:00")
        if (d / "usage.txt").exists():
            s["agents"] = parse_usage(d / "usage.txt")
        if s["facts"] or s["agents"]:
            sprints.append(s)
    return sprints


def gauge(name: str, desc: str, unit: str, points: list[tuple[datetime, float, dict]]) -> dict:
    return {"name": name, "description": desc, "unit": unit, "gauge": {"dataPoints": [
        {"timeUnixNano": str(int(t.timestamp() * 1e9)), "asDouble": v,
         "attributes": [{"key": k, "value": {"stringValue": str(a)}} for k, a in attrs.items()]}
        for t, v, attrs in points]}}


FACTS = {
    "points": "Story points delivered",
    "calls": "Model calls in the sprint",
    "cost": "Weighted cost in million token units (cache read 0.1, cache write 1.25, output 5)",
    "cost_per_point": "Weighted cost per story point (M units)",
    "duration_minutes": "Board span: first to last entry",
    "minutes_per_point": "Board span per story point",
    "questions": "Blocking questions on the board (live-check and skill entries excluded)",
    "questions_unanswered": "Blocking questions never answered on the board",
    "question_wait_max_minutes": "Longest wait for an answer to a blocking question",
    "question_wait_median_minutes": "Median wait for an answer to a blocking question",
    "rework_rounds": "Hand-offs that deliver a rework or follow-up round",
    "blockers": "Blocker entries on the board",
    "board_entries": "Board entries in the sprint",
}


def build_payload(sprints: list[dict]) -> dict:
    metrics = []
    for fact, desc in FACTS.items():
        pts = [(s["end"], float(s["facts"][fact]), {"sprint": s["sprint"]}) for s in sprints if fact in s["facts"]]
        if pts:
            metrics.append(gauge(f"team.sprint.{fact}", desc, "", pts))
    shares = [(s["end"], float(s["facts"][part]), {"sprint": s["sprint"], "part": part})
              for s in sprints for part in ("coordination", "build", "qa") if part in s["facts"]]
    metrics.append(gauge("team.sprint.share", "Share of weighted cost by part", "", shares))
    for key, desc in (("context_per_call", "Average context (cache read + write tokens) per model call"),
                      ("calls", "Model calls"), ("cost", "Weighted cost (M units)")):
        metrics.append(gauge(f"team.agent.{key}", desc, "", [
            (s["end"], float(a[key]), {"sprint": s["sprint"], "agent": a["agent"], "role": a["role"]})
            for s in sprints for a in s["agents"]]))
    return {"resourceMetrics": [{
        "resource": {"attributes": [{"key": k, "value": {"stringValue": v}} for k, v in (
            ("service.name", "agent-team"), ("service.namespace", "wcl-agent"),
            ("app.layer", "build"), ("deployment.environment.name", "dev"))]},
        "scopeMetrics": [{"scope": {"name": "teamstats"}, "metrics": metrics}]}]}


def main() -> None:
    here = Path(__file__).resolve()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--meta", type=Path, default=here.parents[2] / "meta", help="the meta/ directory")
    ap.add_argument("--endpoint", default="http://127.0.0.1:4318", help="Alloy OTLP/HTTP base URL")
    ap.add_argument("--dry-run", action="store_true", help="print the facts, push nothing")
    args = ap.parse_args()

    sprints = collect(args.meta)
    for s in sprints:
        f = s["facts"]
        print(f"{s['sprint']:<12} end {s['end']:%Y-%m-%d %H:%M}Z  pts {f.get('points', '-'):>4}  "
              f"cost/pt {f.get('cost_per_point', '-'):>5}  min {f.get('duration_minutes', 0):>5.0f}  "
              f"q {f.get('questions', '-')}  wait max {f.get('question_wait_max_minutes', 0):>4.0f}  "
              f"rework {f.get('rework_rounds', '-')}  agents {len(s['agents'])}")
    if args.dry_run:
        return
    body = json.dumps(build_payload(sprints)).encode()
    req = urllib.request.Request(args.endpoint.rstrip("/") + "/v1/metrics", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"pushed {len(sprints)} sprints to {args.endpoint} (HTTP {r.status})")
    except OSError as e:
        sys.exit(f"teamstats: push failed ({e}); is Alloy up? docker compose up -d alloy")


if __name__ == "__main__":
    main()
