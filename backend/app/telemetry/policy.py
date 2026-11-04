"""Content-capture policy per environment (feature 054, spec §10).

ADK captures message content by default, so the policy is always explicit: ``dev`` turns
content on (an operator's own value wins), every other environment forces the three lockdown
settings. ADK reads them from ``os.environ`` each time it builds a ``TelemetryConfig``. The
exporter wrappers (``redaction.py``) enforce the same line app-side, in case ADK leaks anyway.
"""

from __future__ import annotations

from collections.abc import Mapping

LOCKDOWN: Mapping[str, str] = {
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "NO_CONTENT",
    "ADK_TELEMETRY_IGNORE_RUN_CONFIG": "1",
}
_DEV_DEFAULTS: Mapping[str, str] = {
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_AND_EVENT",
}
# GenAI semantic conventions (gen_ai.* instead of gcp.vertex.agent.*), spec §6.3.
_SEMCONV = ("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")

# Span and log attributes that carry prompt, response or tool content (ADK legacy and GenAI
# semconv names, HTTP bodies, exception text); outside dev they are removed before export.
CONTENT_ATTRIBUTES = frozenset(
    {
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.call.result",
        "gen_ai.prompt",
        "gen_ai.completion",
        "gcp.vertex.agent.llm_request",
        "gcp.vertex.agent.llm_response",
        "gcp.vertex.agent.tool_call_args",
        "gcp.vertex.agent.tool_response",
        "gcp.vertex.agent.data",
        "http.request.body.content",
        "http.response.body.content",
        # Exception text can quote chat text, tool arguments or SQL parameters (QA SEC-001);
        # exception.type stays.
        "exception.message",
        "exception.stacktrace",
    }
)
_CONTENT_PREFIXES = ("gen_ai.prompt.", "gen_ai.completion.")
# Log events and span events under this prefix exist to carry content (gen_ai.user.message,
# gen_ai.choice, gen_ai.client.inference.operation.details, ...).
CONTENT_EVENT_PREFIX = "gen_ai."
# The content-stream mark Alloy routes on (board contract:content-stream).
CONTENT_FLAG = "app.content"


def is_content_attribute(key: str) -> bool:
    return key in CONTENT_ATTRIBUTES or key.startswith(_CONTENT_PREFIXES)


def content_env(content_allowed: bool, environ: Mapping[str, str]) -> dict[str, str]:
    """The environment variables to set so ADK follows the policy, given the current ones."""
    if content_allowed:
        wanted = {k: v for k, v in _DEV_DEFAULTS.items() if k not in environ}
    else:
        wanted = dict(LOCKDOWN)
    key, value = _SEMCONV
    if key not in environ:
        wanted[key] = value
    return wanted
