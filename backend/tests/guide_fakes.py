"""Shared fake for the guide pipeline (feature 015).

``fake_pipeline`` replaces ``services.guide.run_guide_generation`` with a coroutine that
publishes (or fails) the guide row the way the real pipeline does, without any model call.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide
from backend.app.services.guide_pipeline.models import RunOutcome


def fake_pipeline(monkeypatch, markdown: str = "## Guide", calls: list | None = None, *,
                  outcome: str = "published", cooldowns: list | None = None):
    async def fake(class_name, spec, content_type):
        if calls is not None:
            calls.append((class_name, spec, content_type))
        async with db_session.SessionLocal() as s:
            if outcome == "published":
                await repo.publish_spec_guide(
                    s, class_name=class_name, spec=spec, content_type=content_type,
                    markdown=markdown, brief=None, claims=[], game_patch="12.1", season=None,
                    generated_at=datetime.now(UTC), sources=[], major_cooldowns=cooldowns or [],
                    briefing=None, evidence=None,
                )
            else:
                await repo.fail_spec_guide(
                    s, class_name=class_name, spec=spec, content_type=content_type,
                    reason="model_error",
                )
            await s.commit()
        return RunOutcome(outcome=outcome)

    monkeypatch.setattr(guide, "run_guide_generation", fake)
