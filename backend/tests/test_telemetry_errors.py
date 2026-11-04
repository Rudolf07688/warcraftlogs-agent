"""Feature 054 rework (QA SEC-001): outside dev an error leaves the process as its type only.

The equivalent of the NUL-insert path: a chat turn whose message insert fails. SQLAlchemy's
error text carries the statement's parameters (the user's message), and the error reaches the
turn span, the SQL span's status and a ``logger.exception`` line. Outside dev none of them may
export that text, a message, a stacktrace or a status description.
"""

from __future__ import annotations

import logging

import pytest
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.trace import StatusCode
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.app import telemetry
from backend.app.telemetry import chat_turn_span
from backend.app.telemetry.config import TelemetryConfig
from backend.app.telemetry.redaction import scrub_text
from backend.tests.test_telemetry_support import everything, otel  # noqa: F401 - fixture

USER_TEXT = "my raid leader is Bob, his wcl password is hunter2 USER-TEXT-054"


@pytest.fixture
def failing_turn(engine, monkeypatch):
    """A turn whose insert of the user's message fails, logged the way ws.py logs failures."""
    monkeypatch.setattr(telemetry, "_active", TelemetryConfig(enabled=True, environment="prod", version="t"))
    handler = telemetry.otlp_log_handler()
    log = logging.getLogger("backend.app.test054errors")
    log.addHandler(handler)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, skip_dep_check=True)

    async def run() -> None:
        with pytest.raises(OperationalError):
            with chat_turn_span():
                try:
                    async with engine.connect() as conn:
                        await conn.execute(
                            text("INSERT INTO no_such_messages (content) VALUES (:content)"),
                            {"content": USER_TEXT},
                        )
                except OperationalError:
                    log.exception("turn failed: answer not saved (ref %s)", "abc123")
                    raise

    yield run
    SQLAlchemyInstrumentor().uninstrument()
    log.removeHandler(handler)


@pytest.mark.parametrize("environment", ["ci", "prod", "unknown"])
async def test_outside_dev_an_error_exports_its_type_only(otel, failing_turn, environment):
    capture = otel(environment=environment)
    await failing_turn()

    assert "USER-TEXT-054" not in everything(capture)
    spans = capture.spans()
    failed = [s for s in spans if s.status.status_code is StatusCode.ERROR]
    assert {s.name for s in failed} >= {"chat turn"} and len(failed) >= 2  # the turn and the SQL span
    assert all(s.status.description is None for s in failed)
    [event] = [e for s in spans for e in s.events if e.name == "exception"]
    assert dict(event.attributes)["exception.type"].endswith("OperationalError")
    assert not {"exception.message", "exception.stacktrace"} & set(event.attributes)
    [record] = [r.log_record for r in capture.logs()]
    assert record.body == "turn failed: answer not saved (ref abc123)"
    assert record.attributes["exception.type"] == "OperationalError"
    assert not {"exception.message", "exception.stacktrace"} & set(record.attributes)


async def test_in_dev_the_error_text_stays(otel, failing_turn):
    """Dev shows content, error text included (secret-shaped parts are still masked)."""
    capture = otel(environment="dev")
    await failing_turn()

    exported = everything(capture)
    assert "USER-TEXT-054" in exported and "no_such_messages" in exported


def test_sql_parameters_are_cut_from_any_text_outside_dev():
    error = f"(sqlite3.OperationalError) no such table [SQL: INSERT ...] [parameters: ('{USER_TEXT}',)]"
    assert "USER-TEXT-054" not in scrub_text(error, content_allowed=False)
    assert "[SQL: INSERT ...]" in scrub_text(error, content_allowed=False)
    assert "USER-TEXT-054" in scrub_text(error, content_allowed=True)
