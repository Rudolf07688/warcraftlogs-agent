"""The KNOWN PLAYER CONTEXT preamble (feature 005 / US1)."""

from __future__ import annotations

from backend.app.db.models import GuildProfile, UserCharacter
from backend.app.services.profile_context import build_preamble


def test_empty_profile_yields_empty_preamble():
    # No profile → no preamble, so behavior is unchanged (FR-006).
    assert build_preamble(None, [], None) == ""


def test_preamble_includes_identities_and_scoping_rule():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement", guide_status="none",
    )
    friend = UserCharacter(
        role="friend", name="Aggra", server="Stormrage", region="US", guide_status="none",
    )
    guild = GuildProfile(name="Horde", server="Orgrimmar", region="US", summary_status="none")

    text = build_preamble(self_char, [friend], guild)
    assert "KNOWN PLAYER CONTEXT" in text
    assert "population-level" in text  # the scoping rule is present
    assert "Thrall-Stormrage (US)" in text
    assert "Shaman — Enhancement" in text
    assert "Aggra-Stormrage (US)" in text
    assert "Horde-Orgrimmar (US)" in text


def test_ready_guides_are_included_and_capped():
    big = "x" * 10000
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
        guide_status="ready", guide_markdown=big,
    )
    text = build_preamble(self_char, [], None)
    assert "Spec guides:" in text
    assert "## Thrall — Enhancement" in text
    # The 10k guide is trimmed well below its raw length (per-guide + total caps).
    assert len(text) < 6000


def test_pending_guide_is_not_injected():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        guide_status="pending", guide_markdown=None,
    )
    text = build_preamble(self_char, [], None)
    assert "Spec guides:" not in text
