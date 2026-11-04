"""Feature 054 (sc-406): the exporter-side redaction masks secrets wherever they sit in a span or
log record, with content on, and leaves counts and ordinary text alone."""

from __future__ import annotations

import time

import pytest
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.trace import Link, SpanContext, Status, StatusCode
from opentelemetry._logs import LogRecord

from backend.app.auth.redaction import REDACTED
from backend.app.telemetry import setup
from backend.app.telemetry.redaction import MAX_VALUE_LENGTH, redact_log, redact_span, scrub_text

SECRET = "opaque-SECRET-054"
_CTX = SpanContext(trace_id=1, span_id=2, is_remote=False)


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer opaque-SECRET-054",
        '{"authorization": "Bearer opaque-SECRET-054"}',
        "Basic b3BhcXVlOlNFQ1JFVC0wNTQ=",  # opaque:SECRET-054
        "postgresql+asyncpg://wcl:opaque-SECRET-054@db:5432/wcl",
        "https://example.test/cb?code=opaque-SECRET-054&state=1",
        "https://example.test/v1?key=opaque-SECRET-054",
        '{"client_secret": "opaque-SECRET-054", "n": 1}',
        '{\\"access_token\\": \\"opaque-SECRET-054\\"}',  # JSON encoded twice
        "{'password': 'opaque-SECRET-054'}",
        "WCL_CLIENT_SECRET=opaque-SECRET-054",
        "cookie: __Host-session=opaque-SECRET-054",
    ],
)
def test_secret_shaped_text_is_masked(text):
    assert SECRET not in scrub_text(text)
    assert REDACTED in scrub_text(text)


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX",
        "AIzaSyA1234567890123456789012345678901",
        "ya29.a0AfH6SMBopaque0123456789",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw.SflKxwRJSMeKKF2QT4fw",
    ],
)
def test_known_key_shapes_are_masked_in_free_text(secret):
    assert secret not in scrub_text(f"the model said {secret} in passing")


@pytest.mark.parametrize(
    "text",
    [
        "Basic strategy for Fyrakk: stack for the soak",
        "the bearer of bad news",
        '{"input_tokens": 120, "output_tokens": 7}',
        "max_tokens=1024",
        "https://www.warcraftlogs.com/reports/a1B2c3D4?fight=12",
    ],
)
def test_ordinary_text_and_counts_pass_unchanged(text):
    assert scrub_text(text) == text


def _span(attributes: dict, **kwargs) -> ReadableSpan:
    return ReadableSpan(
        name=kwargs.pop("name", "execute_tool get_report"),
        context=_CTX,
        resource=Resource.create({}),
        attributes=attributes,
        **kwargs,
    )


def test_span_attributes_under_a_sensitive_key_are_masked_whatever_their_shape():
    span = redact_span(
        _span(
            {
                "http.request.header.authorization": [SECRET],
                "app.wcl_client_secret": SECRET,
                "db.dsn": SECRET,
                "gen_ai.usage.input_tokens": 120,
                "gen_ai.request.max_tokens": 1024,
                "http.route": "/api/conversations/{conv_id}",
            }
        ),
        content_allowed=True,
    )
    assert span.attributes["http.request.header.authorization"] == REDACTED
    assert span.attributes["app.wcl_client_secret"] == REDACTED
    assert span.attributes["db.dsn"] == REDACTED
    assert span.attributes["gen_ai.usage.input_tokens"] == 120
    assert span.attributes["gen_ai.request.max_tokens"] == 1024
    assert span.attributes["http.route"] == "/api/conversations/{conv_id}"


def test_span_events_links_status_and_name_are_scrubbed():
    span = redact_span(
        _span(
            {},
            name=f"GET https://x.test/?token={SECRET}",
            events=[Event("exception", {"exception.message": f"401 for Bearer {SECRET}"})],
            links=[Link(_CTX, {"note": f"password={SECRET}"})],
            status=Status(StatusCode.ERROR, f"failed with api_key={SECRET}"),
        ),
        content_allowed=True,
    )
    assert SECRET not in span.name
    assert SECRET not in str(span.events[0].attributes)
    assert SECRET not in str(span.links[0].attributes)
    assert SECRET not in span.status.description
    assert span.context == _CTX and span.status.status_code is StatusCode.ERROR


def test_content_span_events_are_dropped_outside_dev_only():
    events = [Event("gen_ai.user.message", {"content": "hi"}), Event("exception", {})]
    assert [e.name for e in redact_span(_span({}, events=events), content_allowed=False).events] == ["exception"]
    assert len(redact_span(_span({}, events=events), content_allowed=True).events) == 2


def _log(body, attributes: dict | None = None, event_name: str | None = None) -> ReadableLogRecord:
    return ReadableLogRecord(
        log_record=LogRecord(body=body, attributes=attributes or {}, event_name=event_name),
        resource=Resource.create({}),
    )


def test_log_body_and_nested_attributes_are_scrubbed():
    record = redact_log(
        _log(
            {"msg": f"login with Bearer {SECRET}", "headers": {"Cookie": SECRET}},
            {"request": {"api_key": SECRET, "count": 3}},
        ),
        content_allowed=True,
    )
    assert SECRET not in str(record.log_record.body)
    assert record.log_record.attributes["request"] == {"api_key": REDACTED, "count": 3}


def test_a_content_marked_record_is_dropped_outside_dev():
    record = _log("answer text", {"app.content": "true"})
    assert redact_log(record, content_allowed=False) is None
    assert redact_log(record, content_allowed=True).log_record.attributes["app.content"] == "true"


def test_the_original_records_are_not_mutated():
    original = _log(f"Bearer {SECRET}", {"token": SECRET})
    redact_log(original, content_allowed=True)
    assert original.log_record.body == f"Bearer {SECRET}"
    assert original.log_record.attributes["token"] == SECRET


# --- cost is linear and bounded (QA SEC-002, SEC-008) ------------------------------------

ADVERSARIAL = [
    "a" * 16_384,  # one long word: the old key pattern was quadratic here (6.5 s)
    "?" + "a" * 16_383,
    "x://" + "a" * 16_380,
    ("a" * 63 + " ") * 256,
    ("a" * 30 + ":") * 528,
    "a.b-c_" * 2730,
    "xpasswordx " * 1489,
    ";" * 8192 + "a" * 8192,
    "Bearer " * 2340,
]


@pytest.mark.parametrize("text", ADVERSARIAL, ids=range(len(ADVERSARIAL)))
def test_scrubbing_16k_of_adversarial_text_is_fast(text):
    started = time.perf_counter()
    scrub_text(text)
    # Linear work is a few ms; the quadratic pattern took seconds. Generous for a loaded box.
    assert time.perf_counter() - started < 0.5


def test_values_are_capped_before_scrubbing():
    scrubbed = scrub_text("a" * 200_000 + " token=abc")
    assert len(scrubbed) < MAX_VALUE_LENGTH + 32 and scrubbed.endswith("[truncated]")


def test_span_attributes_are_cut_at_the_same_length():
    provider = TracerProvider(span_limits=setup.SPAN_LIMITS)
    with provider.get_tracer("t").start_as_current_span("s") as span:
        span.set_attribute("gen_ai.input.messages", "x" * 100_000)
        assert len(span.attributes["gen_ai.input.messages"]) == MAX_VALUE_LENGTH
    provider.shutdown()
