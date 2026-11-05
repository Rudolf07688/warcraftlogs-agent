#!/usr/bin/env python3
"""Commit facts for the Build vs Runtime dashboard (D12, feature 060, sc-422).

Which seat authored a commit, and what building it cost, as Mimir gauges next to the runtime
metrics, so D12 can put commit, seat, build cost and runtime deltas in one table:

  build_commit_info{commit, seat, feature, sprint}      = 1
  build_commit_cost_usd{commit, seat, feature, sprint}  = estimated USD (only when known)

timestamped at the board entry that names the commit. Sources, all already on disk:

  team board JSONL   meta/sprints/<sprint>/board.jsonl and the live boards (git common dir,
                     team-board/<board>.jsonl): hand-off and merge entries carry the commit as
                     a ref, and their key names the feature (status:<feature>)
  meta/team/*.md     the roster: member name -> seat
  meta/sprints/<sprint>/usage.txt   per-agent tokens (usage.py, written at wrap-up)

Attribution rule (also on the dashboard): a commit belongs to the seat of the latest hand-off
on the same board key at or before the entry that names it; a merge entry with no hand-off on
its key belongs to its own author. Commits are the first 7 characters of the ref, matching the
running version's short SHA. Build cost: the usage rows of the feature (the label starts with
the feature's number, or names its word, and names the seat holder; "-fix" keys match rows
saying "fix", others don't), priced like teamstats.py, booked on the feature's last commit on
the board. With no usage file yet (mid-sprint) the cost is left out, never zero.

  python3 observability/build-runtime/commits.py              # push to Alloy at 127.0.0.1:4318
  python3 observability/build-runtime/commits.py --dry-run    # print the table only
  python3 observability/build-runtime/commits.py --meta DIR --board-dir DIR --endpoint URL

Pushing again is safe (same timestamp, same value). Standard library only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("teamstats", ROOT / ".claude/team/teamstats.py")
teamstats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(teamstats)  # reuse its usage parser, pricing and gauge shape

SHA = re.compile(r"^[0-9a-f]{7,40}$")
COMMIT_KINDS = ("handoff", "merge")


@dataclass
class Commit:
    commit: str
    seat: str
    feature: str
    sprint: str
    ts: datetime
    cost_usd: float | None = None


def seats(team: Path) -> dict[str, str]:
    """Member name (lower case) -> 'name (seat)', from meta/team/<seat>.md."""
    out = {}
    for f in sorted(team.glob("*.md")) if team.is_dir() else []:
        fields = dict(re.findall(r"^- \*\*(\w+):\*\* (.*)$", f.read_text(), re.M))
        if fields.get("name"):
            out[fields["name"].lower()] = f"{fields['name'].lower()} ({fields.get('seat', f.stem)})"
    return out


def board_files(meta: Path, board_dir: Path | None) -> list[tuple[str, Path]]:
    """(sprint, file) for every board: the archived ones in meta/sprints and the live ones."""
    files = [(d.name, d / "board.jsonl") for d in sorted((meta / "sprints").glob("*")) if (d / "board.jsonl").is_file()]
    if board_dir and board_dir.is_dir():
        files += [(f.stem.removeprefix("sprint-"), f) for f in sorted(board_dir.glob("sprint-*.jsonl"))]
    return files


def attribute(entries: list[dict], sprint: str, roster: dict[str, str]) -> list[Commit]:
    """The commits one board names, by the attribution rule in the module docstring."""
    last_handoff: dict[str, str] = {}
    out: dict[str, Commit] = {}
    for e in sorted(entries, key=lambda e: e["id"]):
        key = e.get("key") or ""
        if e["kind"] == "handoff":
            last_handoff[key] = e["author"]
        if e["kind"] not in COMMIT_KINDS or not key.startswith("status:"):
            continue
        author = last_handoff.get(key, e["author"])
        for ref in e.get("refs") or []:
            if SHA.match(ref):
                commit = ref[:7]
                out[commit] = Commit(commit, roster.get(author, author), key.removeprefix("status:"), sprint,
                                     datetime.fromisoformat(e["ts"]))
    return list(out.values())


def feature_rows(feature: str, seat: str, agents: list[dict]) -> list[dict]:
    """Usage rows that built this feature: its number or word, and its seat holder, named."""
    name = seat.split(" ")[0]
    head, fix = re.split(r"[-:]", feature)[0], "fix" in feature
    rows = []
    for a in agents:
        label = a["agent"].lower()
        names_feature = label.startswith(head) if head.isdigit() else bool(re.search(rf"\b{re.escape(head)}\b", label))
        if names_feature and name in label and ("fix" in label) == fix:
            rows.append(a)
    return rows


def collect(meta: Path, board_dir: Path | None) -> list[Commit]:
    roster = seats(meta / "team")
    commits: dict[str, Commit] = {}
    for sprint, path in board_files(meta, board_dir):
        entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        found = attribute(entries, sprint, roster)
        usage = meta / "sprints" / sprint / "usage.txt"
        agents = teamstats.parse_usage(usage) if usage.is_file() else []
        last: dict[str, Commit] = {}
        for c in found:
            if c.feature not in last or c.ts >= last[c.feature].ts:
                last[c.feature] = c
        for c in last.values():
            rows = feature_rows(c.feature, c.seat, agents)
            if rows:
                c.cost_usd = round(sum(r["cost"] for r in rows) * teamstats.INPUT_USD_PER_M, 2)
        for c in found:
            commits[c.commit] = c  # an archived board and its live copy name the same commits
    return sorted(commits.values(), key=lambda c: c.ts)


def payload(commits: list[Commit]) -> dict:
    def labels(c: Commit) -> dict:
        return {"commit": c.commit, "seat": c.seat, "feature": c.feature, "sprint": c.sprint}

    metrics = [teamstats.gauge("build.commit.info", "A board hand-off or merge names this commit (1)", "",
                               [(c.ts, 1.0, labels(c)) for c in commits])]
    costed = [(c.ts, c.cost_usd, labels(c)) for c in commits if c.cost_usd is not None]
    if costed:
        metrics.append(teamstats.gauge(
            "build.commit.cost_usd", f"Estimated build cost of the feature, USD at {teamstats.LIST_PRICE_MODEL} list price", "", costed))
    return {"resourceMetrics": [{
        "resource": {"attributes": [{"key": k, "value": {"stringValue": v}} for k, v in (
            ("service.name", "agent-team"), ("service.namespace", "wcl-agent"),
            ("app.layer", "build"), ("deployment.environment.name", "dev"))]},
        "scopeMetrics": [{"scope": {"name": "build-runtime"}, "metrics": metrics}]}]}


def live_board_dir() -> Path | None:
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                                capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(common) / "team-board"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--meta", type=Path, default=ROOT / "meta", help="the meta/ directory")
    ap.add_argument("--board-dir", type=Path, default=None, help="live boards (default: <git common dir>/team-board)")
    ap.add_argument("--endpoint", default="http://127.0.0.1:4318", help="Alloy OTLP/HTTP base URL")
    ap.add_argument("--dry-run", action="store_true", help="print the table, push nothing")
    args = ap.parse_args()

    commits = collect(args.meta, args.board_dir or live_board_dir())
    for c in commits:
        cost = f"{c.cost_usd:8.2f}" if c.cost_usd is not None else "       -"
        print(f"{c.ts:%Y-%m-%d %H:%M}Z  {c.commit}  {c.seat:<18} {c.feature:<14} {c.sprint:<12} {cost}")
    if args.dry_run or not commits:
        return
    req = urllib.request.Request(args.endpoint.rstrip("/") + "/v1/metrics", data=json.dumps(payload(commits)).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"pushed {len(commits)} commits to {args.endpoint} (HTTP {r.status})")
    except OSError as e:
        sys.exit(f"commits: push failed ({e}); is Alloy up? docker compose up -d alloy")


if __name__ == "__main__":
    main()
