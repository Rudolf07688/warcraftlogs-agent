"""Where models run, and what Vertex's Model Garden lists (feature 016).

This is the only module that knows the model location. Every client that calls a model
(chat, web search, guides, reports, greeting, suggestions, discovery probes) is built here
or takes ``model_location()`` from here, so ``GOOGLE_CLOUD_LOCATION`` is free to name a
regional location for everything else. ``europe-west1`` serves only Gemini 2.5 and no
Claude; ``global`` serves every current model (checked live 2026-10-18).

The catalog listing uses the REST ``v1beta1`` endpoint because only it returns each
model's ``launchStage``. All calls here are blocking; discovery runs them in threads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from anthropic import AnthropicVertex, AsyncAnthropicVertex
    from google import genai

Publisher = Literal["google", "anthropic"]

CATALOG_URL = "https://aiplatform.googleapis.com/v1beta1/publishers/{publisher}/models"
CATALOG_TIMEOUT_S = 10
_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


def uses_vertex() -> bool:
    """Whether Gemini runs on Vertex (``GOOGLE_GENAI_USE_VERTEXAI``), as google-genai reads it.

    False means the AI Studio API-key setup: clients are built plainly from the
    environment, and there is no Model Garden catalog or location to choose.
    """
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes"}


def model_location() -> str:
    """``WCL_MODEL_LOCATION``, default ``global``: where every model call runs."""
    return os.getenv("WCL_MODEL_LOCATION", "").strip() or "global"


def project_id() -> str | None:
    """``GOOGLE_CLOUD_PROJECT``, else the project of the application default credentials."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    if project:
        return project
    try:
        import google.auth

        return google.auth.default()[1]
    except Exception:  # noqa: BLE001 - no ADC at all: the caller decides what that means
        return None


# --- model clients ------------------------------------------------------------------------


def adk_client_kwargs() -> dict[str, Any]:
    """``client_kwargs`` for an ADK ``Gemini``: Vertex at the model location, or none."""
    return {"vertexai": True, "location": model_location()} if uses_vertex() else {}


def genai_client() -> genai.Client:
    from google import genai

    if not uses_vertex():
        return genai.Client()  # API-key setup: GOOGLE_API_KEY from the environment
    return genai.Client(vertexai=True, project=project_id(), location=model_location())


def anthropic_client(**kwargs: Any) -> AnthropicVertex:
    from anthropic import AnthropicVertex

    return AnthropicVertex(project_id=project_id(), region=model_location(), **kwargs)


def async_anthropic_client(**kwargs: Any) -> AsyncAnthropicVertex:
    from anthropic import AsyncAnthropicVertex

    return AsyncAnthropicVertex(project_id=project_id(), region=model_location(), **kwargs)


# --- the Model Garden catalog -------------------------------------------------------------


@dataclass(frozen=True)
class CatalogEntry:
    """One row of a publisher's catalog listing."""

    publisher: Publisher
    name: str  # last segment of the resource name, e.g. "gemini-3.8-flash"
    version_id: str | None  # "default" or a release tag such as "20251001"
    stage: str | None  # launchStage: GA, PUBLIC_PREVIEW, EXPERIMENTAL, ...


class CatalogUnavailable(Exception):
    """The catalog could not be listed (transport, auth, HTTP status or response shape)."""


def _session() -> Any:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=list(_SCOPES))
    return AuthorizedSession(credentials)


def list_publisher_models(publisher: Publisher) -> list[CatalogEntry]:
    """Every model ``publisher`` lists on the global endpoint, following pagination."""
    try:
        session = _session()
        project = project_id()
        headers = {"x-goog-user-project": project} if project else {}
        url = CATALOG_URL.format(publisher=publisher)
        entries: list[CatalogEntry] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            response = session.get(url, params=params, headers=headers, timeout=CATALOG_TIMEOUT_S)
            response.raise_for_status()
            body = response.json()
            for row in body.get("publisherModels", []):
                entries.append(
                    CatalogEntry(
                        publisher=publisher,
                        name=row["name"].rsplit("/", 1)[-1],
                        version_id=row.get("versionId"),
                        stage=row.get("launchStage"),
                    )
                )
            token = body.get("nextPageToken")
            if not token:
                return entries
    except Exception as exc:  # every failure means the same thing to discovery
        raise CatalogUnavailable(f"{publisher}: {type(exc).__name__}: {exc}") from exc
