"""US2/US4: distinct-encounter extraction + merge."""

from __future__ import annotations

from backend.app.services.encounters import encounters_from_tool, merge_encounters


def test_encounters_from_tool_dedups_and_marks_kill():
    result = {
        "status": "success",
        "fights": [
            {"id": 1, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": False},
            {"id": 2, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": True},
            {"id": 3, "name": "Sikran", "encounterID": 2917, "difficulty": 5, "kill": False},
            {"id": 4, "name": "Trash", "encounterID": 0, "kill": False},
            {"id": 5, "name": "More trash", "encounterID": None, "kill": False},
        ],
    }
    enc = encounters_from_tool("get_report_fights", True, result)
    by_id = {e["encounter_id"]: e for e in enc}
    assert set(by_id) == {2902, 2917}  # deduped; trash/null excluded
    assert by_id[2902]["kill"] is True  # any pull a kill => kill
    assert by_id[2917]["kill"] is False
    assert by_id[2902]["name"] == "Ulgrax"


def test_encounters_from_tool_ignores_other_tools_and_failures():
    assert encounters_from_tool("get_report_table", True, {"status": "success"}) == []
    assert encounters_from_tool("get_report_fights", False, {"status": "error"}) == []
    assert encounters_from_tool("get_report_fights", True, {"fights": "nope"}) == []


def test_merge_encounters_no_duplicates_and_upgrades_kill():
    a = [{"encounter_id": 2902, "name": "Ulgrax", "difficulty": 5, "kill": False}]
    b = [
        {"encounter_id": 2902, "name": "Ulgrax", "difficulty": 5, "kill": True},
        {"encounter_id": 2917, "name": "Sikran", "difficulty": 5, "kill": False},
    ]
    merged = merge_encounters(a, b)
    by_id = {e["encounter_id"]: e for e in merged}
    assert set(by_id) == {2902, 2917}
    assert by_id[2902]["kill"] is True


def test_merge_encounters_handles_none():
    assert merge_encounters(None, None) == []
    out = merge_encounters(None, [{"encounter_id": 1, "name": "X"}])
    assert [e["encounter_id"] for e in out] == [1]
