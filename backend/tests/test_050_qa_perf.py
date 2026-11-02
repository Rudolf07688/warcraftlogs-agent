"""QA sweep 2026-11-02 performance fixes on the 050 code (PERF-001, PERF-002, PERF-005).

Neutralising runs only on what a table result keeps, ASCII text skips it exactly, the bracket
map is a literal (regenerated here from its rule), and the knowledge-search cap renders each hit
once. No timing assertions: call counts and exactness instead.
"""

from __future__ import annotations

import html
import json
import unicodedata
from pathlib import Path

from backend.app.kb import search as kb
from backend.app.kb.search import Hit, SearchResult
from wcl_agent.tools import report_tools
from wcl_agent.tools.report_tools import compact_table, neutralise, overview_table

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "wcl_table_heroic_20.json").read_text())
_OPEN_NAMES = ("LESS-THAN", "LEFT-POINTING", "LEFT ANGLE", "LEFT DOUBLE ANGLE", "LEFT ARROWHEAD", "PRECEDES")
_CLOSE_NAMES = ("GREATER-THAN", "RIGHT-POINTING", "RIGHT ANGLE", "RIGHT DOUBLE ANGLE", "RIGHT ARROWHEAD", "SUCCEEDS")


def _strings(obj) -> int:
    if isinstance(obj, dict):
        return sum(_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_strings(v) for v in obj)
    return isinstance(obj, str)


def test_the_bracket_literal_is_what_its_rule_generates():
    opens, closes = {"ᐸ"}, {"ᐳ"}  # Canadian syllabics PA, PO
    for cp in range(0x30000):
        name = unicodedata.name(chr(cp), "")
        if any(part in name for part in _OPEN_NAMES):
            opens.add(chr(cp))
        elif any(part in name for part in _CLOSE_NAMES):
            closes.add(chr(cp))
    assert set(report_tools._OPEN_BRACKETS) == opens
    assert set(report_tools._CLOSE_BRACKETS) == closes


def test_the_ascii_fast_path_is_exact():
    # every step of the slow path leaves these characters alone, so skipping it changes nothing
    for c in map(chr, range(128)):
        if c in "&<>":
            continue
        assert html.unescape(c) == c and unicodedata.normalize("NFKC", c) == c
        assert unicodedata.category(c) != "Cf" and c not in report_tools._BRACKET_MAP
    text = "Raider-Silvermoon (Fire) 1,044,432.0 dps; [boss_19.jpg] {x} 'q' \"q\" \t\n"
    assert neutralise(text) is text
    assert neutralise("a < b & c") == "a ( b & c"  # anything else still takes the full path


def _count_neutralise(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = report_tools.neutralise

    def counting(text: str) -> str:
        seen.append(text)
        return real(text)

    monkeypatch.setattr(report_tools, "neutralise", counting)
    return seen


def test_projections_neutralise_only_the_strings_they_keep(monkeypatch):
    summary = FIXTURE["Summary"]
    assert _strings(summary) > 3_000
    seen = _count_neutralise(monkeypatch)
    out = overview_table(summary)
    assert len(seen) == _strings(out["data"])
    seen.clear()
    out = compact_table(summary)
    # the size check may project at several widths; never anything like the whole raw table
    assert out["_compact"] is True and len(seen) <= 3 * _strings(out["data"]) < _strings(summary) / 2


def test_a_small_table_is_neutralised_once(monkeypatch):
    table = {"data": {"totalTime": 1000, "entries": [{"name": "Thornak", "id": 1, "total": 5}]}}
    seen = _count_neutralise(monkeypatch)
    assert compact_table(table) == table
    assert seen == ["Thornak"]


def test_the_search_cap_renders_each_hit_once(monkeypatch):
    hits = [Hit("wcl", {"report_code": "Ab12Cd34", "fight_id": i, "label": f"fight {i} été"},
                "é" * 400, 0.5 - i / 100) for i in range(15)]
    calls: list[Hit] = []
    real = kb._item

    def counting(hit: Hit):
        calls.append(hit)
        return real(hit)

    monkeypatch.setattr(kb, "_item", counting)
    capped = kb.cap(SearchResult(hits, "hybrid", []))
    assert capped.capped is True and 0 < len(capped.hits) < len(hits)
    assert len(calls) == len(hits)
    monkeypatch.undo()
    assert kb._size(capped) <= kb.OUTPUT_CAP < kb._size(SearchResult(hits[: len(capped.hits) + 1], "hybrid", [], capped=True))
