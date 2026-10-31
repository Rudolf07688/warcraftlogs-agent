"""Which LLM provider serves the app, and every model client it uses (feature 032).

``WCL_LLM_PROVIDER`` picks one provider per process: ``vertex`` (the default: Gemini, and Claude
through Vertex's Model Garden) or ``anthropic`` (Claude through the Anthropic API with
``ANTHROPIC_API_KEY``). This module is the only code that reads either variable and the only code
that constructs a model client; call sites ask it for a client or a role's model and never compare
the provider themselves. ``vertex.py`` keeps what is Vertex-only: the model location, the project
and the Model Garden catalog.

The key is held as a ``SecretStr`` and passed straight into the client; no other code sees it.
"""

from __future__ import annotations

import functools
import logging
import os
import re
from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import SecretStr

from .vertex import model_location, project_id, uses_vertex

if TYPE_CHECKING:
    from anthropic import Anthropic, AnthropicVertex, AsyncAnthropic, AsyncAnthropicVertex
    from google import genai

logger = logging.getLogger(__name__)

Provider = Literal["vertex", "anthropic"]
_PROVIDERS: tuple[Provider, ...] = ("vertex", "anthropic")


class ModelRole(StrEnum):
    """A fixed use of a model; each has a default per provider and an env override."""

    CHAT = "chat"
    REPORT = "report"
    GUIDE = "guide"
    GUIDE_REVIEW = "guide_review"
    FAST = "fast"  # follow-up suggestions and chat titles
    GREETING = "greeting"


ROLE_ENV: dict[ModelRole, str] = {
    ModelRole.CHAT: "WCL_DEFAULT_MODEL",
    ModelRole.REPORT: "WCL_REPORT_MODEL",
    ModelRole.GUIDE: "WCL_GUIDE_MODEL",
    ModelRole.GUIDE_REVIEW: "WCL_GUIDE_REVIEW_MODEL",
    ModelRole.FAST: "WCL_SUGGEST_MODEL",
    ModelRole.GREETING: "WCL_GREETING_MODEL",
}

# The vertex column is the pre-032 behaviour. The anthropic one follows D5/D9: a fast model for the
# light roles, a mid model for chat, reports and authoring, a stronger, different reviewer.
ROLE_DEFAULTS: dict[Provider, dict[ModelRole, str]] = {
    "vertex": {
        ModelRole.CHAT: "gemini-3.6-flash",
        ModelRole.REPORT: "gemini-3.6-flash",
        ModelRole.GUIDE: "gemini-3.7-flash",
        ModelRole.GUIDE_REVIEW: "gemini-3.1-pro-preview",
        ModelRole.FAST: "gemini-3.6-flash",
        ModelRole.GREETING: "gemini-3.5-flash-lite",
    },
    "anthropic": {
        ModelRole.CHAT: "claude-sonnet-5-5",
        ModelRole.REPORT: "claude-sonnet-5-5",
        ModelRole.GUIDE: "claude-sonnet-5-5",
        ModelRole.GUIDE_REVIEW: "claude-opus-5-5",
        ModelRole.FAST: "claude-haiku-5-5",
        ModelRole.GREETING: "claude-haiku-5-5",
    },
}


class LlmProviderNotConfigured(RuntimeError):
    """The active provider lacks its credential. The message never carries a secret."""


@functools.cache
def active_provider() -> Provider:
    """``WCL_LLM_PROVIDER`` (trimmed, any case); unset or unknown means ``vertex``. Read once."""
    raw = os.getenv("WCL_LLM_PROVIDER", "")
    value = raw.strip().lower()
    if not value:
        return "vertex"
    if value in _PROVIDERS:
        return value  # type: ignore[return-value]
    logger.warning("WCL_LLM_PROVIDER=%r is not vertex or anthropic; using vertex", raw)
    return "vertex"


def _api_key() -> SecretStr | None:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return SecretStr(key) if key else None


def credentials_error() -> str | None:
    """Why the active provider can't build its clients, as one key-free sentence; else None.

    Vertex credentials (ADC) are resolved by the Google libraries when a call runs, as before.
    """
    if active_provider() == "anthropic" and _api_key() is None:
        return (
            "WCL_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; Claude calls fail "
            "until it is set in .env and the backend restarts"
        )
    return None


def has_model_catalog() -> bool:
    """Whether startup discovery can list a model catalog (Vertex's Model Garden only)."""
    return active_provider() == "vertex"


# --- model ids ----------------------------------------------------------------------------

# Dated Claude ids: the Anthropic API writes ``name-YYYYMMDD``, Vertex ``name@YYYYMMDD``.
# Undated ids (``claude-sonnet-5-5``) and Gemini ids are the same everywhere.
_VERTEX_DATED = re.compile(r"^(claude-.+)@(\d{8})$")
_API_DATED = re.compile(r"^(claude-.+)-(\d{8})$")


def serves(model_id: str) -> bool:
    """Whether the active provider can run ``model_id`` (the Anthropic API runs only Claude)."""
    from .model_retry import is_anthropic_model  # model_retry imports this module

    return active_provider() == "vertex" or is_anthropic_model(model_id)


def to_provider_id(model_id: str) -> str:
    """``model_id`` in the active provider's form: the one place ids are rewritten."""
    model_id = model_id.strip()
    if active_provider() == "anthropic":
        return _VERTEX_DATED.sub(r"\1-\2", model_id)
    return _API_DATED.sub(r"\1@\2", model_id)


def served_ids(ids: Iterable[str]) -> list[str]:
    """The ids the active provider serves, in its form, de-duplicated, order kept."""
    return list(dict.fromkeys(to_provider_id(m) for m in ids if m.strip() and serves(m)))


def default_candidates() -> list[str]:
    """Ids to probe at startup when none are configured: none on Vertex, the Claude roles' else."""
    if active_provider() == "vertex":
        return []
    return list(dict.fromkeys(ROLE_DEFAULTS["anthropic"].values()))


_warned_roles: set[ModelRole] = set()


def role_model(role: ModelRole, explicit: str | None = None) -> str:
    """The model for ``role``: ``explicit`` (else its env variable) if the active provider serves
    it, in the provider's form; otherwise the provider's default for the role.

    A set but unservable value (a Gemini id under ``anthropic``) is ignored with one warning per
    role, so switching providers takes one ``.env`` line (sc-249 AC 7).
    """
    value = (os.getenv(ROLE_ENV[role], "") if explicit is None else explicit).strip()
    default = ROLE_DEFAULTS[active_provider()][role]
    if not value:
        return default
    if serves(value):
        return to_provider_id(value)
    if role not in _warned_roles:
        _warned_roles.add(role)
        logger.warning(
            "%s=%s is not served by the %s provider; using %s",
            ROLE_ENV[role],
            value,
            active_provider(),
            default,
        )
    return default


# --- model clients ------------------------------------------------------------------------


def adk_client_kwargs() -> dict[str, Any]:
    """``client_kwargs`` for an ADK ``Gemini``: Vertex at the model location, or none."""
    return {"vertexai": True, "location": model_location()} if uses_vertex() else {}


def genai_client() -> genai.Client:
    from google import genai

    if not uses_vertex():
        return genai.Client()  # API-key setup: GOOGLE_API_KEY from the environment
    return genai.Client(vertexai=True, project=project_id(), location=model_location())


def _require_key() -> SecretStr:
    key = _api_key()
    if key is None:
        raise LlmProviderNotConfigured(credentials_error())
    return key


def anthropic_client(**kwargs: Any) -> Anthropic | AnthropicVertex:
    """The blocking Claude client of the active provider (discovery probes)."""
    if active_provider() == "anthropic":
        from anthropic import Anthropic

        return Anthropic(api_key=_require_key().get_secret_value(), **kwargs)
    from anthropic import AnthropicVertex

    return AnthropicVertex(project_id=project_id(), region=model_location(), **kwargs)


def async_anthropic_client(**kwargs: Any) -> AsyncAnthropic | AsyncAnthropicVertex:
    """The async Claude client of the active provider (the ADK agent's ``RetryingClaude``)."""
    if active_provider() == "anthropic":
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=_require_key().get_secret_value(), **kwargs)
    from anthropic import AsyncAnthropicVertex
    from google.adk.utils._google_client_headers import get_tracking_headers

    kwargs.setdefault("default_headers", get_tracking_headers())
    return AsyncAnthropicVertex(project_id=project_id(), region=model_location(), **kwargs)
