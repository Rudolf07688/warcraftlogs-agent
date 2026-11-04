"""teamstats.py: cost per board seat and sprint for D2 (feature 055, sc-408)."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / ".claude" / "team" / "teamstats.py"
_spec = importlib.util.spec_from_file_location("teamstats", _PATH)
teamstats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(teamstats)

ROSTER_FILES = {
    "dev-1": "Ansel", "dev-2": "Tomas", "dev-3": "Nils", "po": "Maren", "sm": "Ilse", "lead": "team-lead",
}


@pytest.fixture
def meta(tmp_path: Path) -> Path:
    (tmp_path / "team-optimisation.md").write_text("no baseline rows\n")
    team = tmp_path / "team"
    team.mkdir()
    for seat, name in ROSTER_FILES.items():
        (team / f"{seat}.md").write_text(f"# {name}\n\n- **name:** {name}\n- **seat:** {seat}\n- **role:** x\n")
    sprint = tmp_path / "sprints" / "2026-11-04"
    sprint.mkdir(parents=True)
    (sprint / "usage.txt").write_text(
        "agent                                     calls      out     cacheRd    cacheWr  sends\n"
        "main (team-lead)                            10    100000     1000000     100000      0\n"
        "054 backend telemetry (Nils)                10    200000     2000000     200000      0\n"
        "QA fix round Nils                           10    100000           0          0      0\n"
        "Dev-1: feature 036 hardening                10         0    10000000          0      0\n"
        "QA security sweep                           10     10000           0          0      0\n"
        "product-owner                               10         0           0    1000000      0\n"
        "TOTAL {'calls': 60}\n")
    return tmp_path


@pytest.mark.parametrize(("label", "seat"), [
    ("main (team-lead)", "team-lead"),
    ("product-owner", "maren"),
    ("054 backend telemetry (Nils)", "nils"),
    ("QA fix round Ansel", "ansel"),
    ("Dev-2: feature 037 hardening", "tomas"),
    ("Architecture docs close-out (Tomas)", "tomas"),
    ("QA security sweep", "unattributed"),
    ("Dev 050 report fights", "unattributed"),
    ("dev-a-018", "unattributed"),  # worktree letters from before the seats, not a seat
])
def test_seat_of(meta: Path, label: str, seat: str) -> None:
    assert teamstats.seat_of(label, teamstats.parse_roster(meta / "team")) == seat


def test_seat_cost_sums_agents_per_seat_at_list_price(meta: Path) -> None:
    sprints = teamstats.collect(meta)
    payload = teamstats.build_payload(sprints)
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    seat = next(m for m in metrics if m["name"] == "team.seat.cost_usd")
    got = {next(a["value"]["stringValue"] for a in p["attributes"] if a["key"] == "seat"): p["asDouble"]
           for p in seat["gauge"]["dataPoints"]}
    price = teamstats.INPUT_USD_PER_M
    # weighted M units: cache read 0.1, cache write 1.25, output 5 (input price ratios)
    assert got["nils"] == pytest.approx((2_000_000 * 0.1 + 200_000 * 1.25 + 300_000 * 5) / 1e6 * price)
    assert got["team-lead"] == pytest.approx((1_000_000 * 0.1 + 100_000 * 1.25 + 100_000 * 5) / 1e6 * price)
    assert got["ansel"] == pytest.approx(10_000_000 * 0.1 / 1e6 * price)
    assert got["maren"] == pytest.approx(1_000_000 * 1.25 / 1e6 * price)
    assert got["unattributed"] == pytest.approx(10_000 * 5 / 1e6 * price)
    stamp = int(datetime(2026, 11, 4, 17, tzinfo=timezone.utc).timestamp() * 1e9)
    assert {p["timeUnixNano"] for p in seat["gauge"]["dataPoints"]} == {str(stamp)}
    assert "estimated" in seat["description"] and "list price" in seat["description"]
