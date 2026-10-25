"""Startup model discovery + validation (US4; feature 016).

Two ways to build the chat model set, chosen by ``mode``:

- ``catalog`` (feature 016): list Vertex's Model Garden catalog for Google and Anthropic,
  sort each entry into a class (Gemini pro / flash / flash-lite, Claude haiku / sonnet /
  opus), probe the newest few versions of every class in one concurrent wave, and keep
  the newest ``keep`` that answer. If the catalog can't be listed, the static lists are
  probed instead (``source="fallback"``).
- ``static``: probe the configured ``.env`` ids and keep the ones that answer.

Every probe is a one-token call that carries one dummy function declaration, so a model
that rejects tools (the chat agent always sends them) is never offered. The result is
computed once at backend startup (and shared through the ``model_catalog`` cache family)
and served from ``app.state``; there is no per-request probing.

If nothing passes, or no probe can run at all, the documented fallback set is returned
with ``degraded=True`` so the UI can show a notice and the selector is never empty
(FR-016). All calls here are blocking and are expected to run under
``asyncio.to_thread`` (see backend lifespan).
"""

from __future__ import annotations

import contextvars
import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, TypeVar

from . import vertex
from ..cache.cache_models import ClassResult, ModelCatalog
from .vertex import CatalogEntry, CatalogUnavailable

T = TypeVar("T")

logger = logging.getLogger(__name__)


def _gather_threads(calls: list[Callable[[], T]], max_workers: int = 4) -> list[T | BaseException]:
    """Run blocking SDK probes concurrently; results in input order, errors in their slot."""
    if not calls:
        return []

    def capture(call: Callable[[], T]) -> T | BaseException:
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - handed back to the caller in its slot
            return exc

    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as pool:
        futures = [pool.submit(contextvars.copy_context().run, capture, c) for c in calls]
        return [f.result() for f in futures]


def _is_anthropic(model: str) -> bool:
    return "claude" in model.lower()


# --- classes and candidates (feature 016, research R2) -------------------------------------

GEMINI_CLASSES = ("pro", "flash", "flash-lite")
ANTHROPIC_CLASSES = ("haiku", "sonnet", "opus")
ALLOWED_STAGES = frozenset({"GA", "PUBLIC_PREVIEW"})
_CLASS_NAMES = {"google": GEMINI_CLASSES, "anthropic": ANTHROPIC_CLASSES}

# flash-lite comes before flash in the alternation so it is never read as flash. The
# anchors drop TTS, image, live, embedding, dated previews, fable and claude-3-opus.
_GEMINI_RE = re.compile(r"^gemini-(\d+)(?:\.(\d+))?-(pro|flash-lite|flash)(-preview)?$")
_CLAUDE_RE = re.compile(r"^claude-(haiku|sonnet|opus)-(\d+)(?:-(\d+))?$")


@dataclass(frozen=True)
class ClassSetting:
    """One configured model class and how many of its newest working versions to serve."""

    publisher: Literal["google", "anthropic"]
    name: str
    keep: int


@dataclass(frozen=True)
class Candidate:
    """A catalog entry that matched a configured class."""

    publisher: str
    cls: str
    version: tuple[int, int]
    preview: bool
    model_id: str  # what the provider accepts: bare, or name@version for dated Claude


class ProbeOutcome(StrEnum):
    PASSED = "passed"
    NOT_ENABLED = "not_enabled"  # 404 / 403
    NO_QUOTA = "no_quota"  # 429, still after one retry
    FAILED = "failed"  # timeout or any other error


def parse_class_settings(publisher: Literal["google", "anthropic"], raw: str) -> list[ClassSetting]:
    """``"pro:2,flash:2"`` → settings in the given order; bad entries are warned and skipped."""
    settings: list[ClassSetting] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        name, _, count = item.partition(":")
        name = name.strip().lower()
        try:
            keep = int(count)
        except ValueError:
            keep = 0
        if name not in _CLASS_NAMES[publisher] or keep < 1:
            logger.warning(
                "ignoring model class setting %r for %s: expected one of %s with a positive count",
                item,
                publisher,
                ", ".join(_CLASS_NAMES[publisher]),
            )
            continue
        settings.append(ClassSetting(publisher, name, keep))
    return settings


def callable_id(entry: CatalogEntry) -> str:
    """The id a call uses: Claude pins a dated version as ``name@version``."""
    if entry.publisher == "anthropic" and entry.version_id not in (None, "", "default"):
        return f"{entry.name}@{entry.version_id}"
    return entry.name


def classify(entry: CatalogEntry, classes: Sequence[ClassSetting]) -> Candidate | None:
    """The candidate ``entry`` is for one of ``classes``, or None."""
    if entry.stage is not None and entry.stage not in ALLOWED_STAGES:
        return None  # EXPERIMENTAL and anything unknown; a missing stage is left to the probe
    if entry.publisher == "google":
        match = _GEMINI_RE.match(entry.name)
        if match is None:
            return None
        major, minor, cls, preview_suffix = match.groups()
    else:
        match = _CLAUDE_RE.match(entry.name)
        if match is None:
            return None
        cls, major, minor = match.groups()
        preview_suffix = None
    if not any(c.publisher == entry.publisher and c.name == cls for c in classes):
        return None
    return Candidate(
        publisher=entry.publisher,
        cls=cls,
        version=(int(major), int(minor or 0)),
        preview=bool(preview_suffix) or entry.stage == "PUBLIC_PREVIEW",
        model_id=callable_id(entry),
    )


def candidates_by_class(
    entries: Iterable[CatalogEntry], classes: Sequence[ClassSetting]
) -> dict[tuple[str, str], list[Candidate]]:
    """Candidates per ``(publisher, class)``: newest first, GA before preview on a tie."""
    out: dict[tuple[str, str], list[Candidate]] = {(c.publisher, c.name): [] for c in classes}
    for entry in entries:
        candidate = classify(entry, classes)
        if candidate is not None:
            out[(candidate.publisher, candidate.cls)].append(candidate)
    for found in out.values():
        found.sort(key=lambda c: (-c.version[0], -c.version[1], c.preview))
    return out


def pick_per_class(
    setting: ClassSetting, candidates: Sequence[Candidate], outcomes: Mapping[str, ProbeOutcome]
) -> ClassResult:
    """Walk ``candidates`` newest first and keep up to ``setting.keep`` that passed.

    ``not_enabled`` / ``failed`` move on to the next version; ``no_quota`` stops the class,
    because the provider enforces quota per base model. A candidate with no outcome
    (its client could not be built) counts as failed.
    """
    kept: list[str] = []
    failed: list[str] = []
    first_failure: str | None = None
    reason: str | None = None
    for candidate in candidates:
        if len(kept) >= setting.keep:
            break
        outcome = outcomes.get(candidate.model_id, ProbeOutcome.FAILED)
        if outcome is ProbeOutcome.PASSED:
            kept.append(candidate.model_id)
        elif outcome is ProbeOutcome.NO_QUOTA:
            reason = ProbeOutcome.NO_QUOTA.value
            break
        else:
            first_failure = first_failure or outcome.value
            if outcome is ProbeOutcome.FAILED:
                failed.append(candidate.model_id)
    if reason is None and not kept:
        reason = first_failure or "no_candidates"
    return ClassResult(
        publisher=setting.publisher, cls=setting.name, models=kept, reason=reason, failed=failed
    )


def has_transient_gaps(classes: Sequence[ClassResult]) -> bool:
    """Whether a class lost a model to something a later boot may not see again.

    That is a failed probe (timeout, 5xx), or a Gemini 429: Gemini quota is shared and
    dynamic. A Claude 429 means the class has no quota granted, which only changes in
    the Cloud console, so it counts as settled.
    """
    return any(
        r.failed or (r.reason == ProbeOutcome.NO_QUOTA.value and r.publisher == "google")
        for r in classes
    )


def is_catalog_id(model_id: str) -> bool:
    """Whether ``model_id`` has the shape discovery serves (a cached value is re-checked).

    Gemini ids are bare class names; Claude ids may pin a dated version. Anything else,
    such as a ``projects/…`` resource path, is rejected.
    """
    name, _, version = model_id.partition("@")
    if _GEMINI_RE.match(name):
        return not version
    if _CLAUDE_RE.match(name):
        return not version or version.isdigit()
    return False


def model_class(model_id: str) -> tuple[str, str] | None:
    """``(publisher, class)`` of a served id by the discovery naming rules, else None.

    A dated Claude id (``name@version``) is classified by its name.
    """
    name = model_id.partition("@")[0]
    if match := _GEMINI_RE.match(name):
        return "google", match.group(3)
    if match := _CLAUDE_RE.match(name):
        return "anthropic", match.group(1)
    return None


def class_label(model_id: str) -> str | None:
    """``"Gemini flash"`` / ``"Claude sonnet"`` for a user-facing message, else None."""
    found = model_class(model_id)
    if found is None:
        return None
    publisher, cls = found
    return f"{'Gemini' if publisher == 'google' else 'Claude'} {cls}"


def sibling_model(model: str, served: Sequence[str]) -> str | None:
    """The served model a rate-limited ``model`` falls back to (feature 021), or None.

    Peers are the served ids of the same publisher and class, in served order (newest
    first in catalog mode). The first peer falls back to the second; any other peer
    falls back to the first. A class with one served model has no sibling.
    """
    found = model_class(model)
    if found is None:
        return None
    peers = [m for m in served if model_class(m) == found]
    if model not in peers:
        return None
    if peers[0] != model:
        return peers[0]
    return peers[1] if len(peers) > 1 else None


def choose_default(models: Sequence[str], configured: str, classes: Sequence[ClassResult]) -> str:
    """The configured default if served, else the newest flash, else the first model."""
    if configured in models:
        return configured
    for result in classes:
        if result.publisher == "google" and result.cls == "flash" and result.models:
            return result.models[0]
    return models[0]


_REASON_TEXT = {
    ProbeOutcome.NO_QUOTA.value: "no quota (429)",
    ProbeOutcome.NOT_ENABLED.value: "not enabled",
    ProbeOutcome.FAILED.value: "failed",
    "no_candidates": "no candidates",
}


def log_class_results(classes: Sequence[ClassResult]) -> None:
    """One INFO line per class, e.g. ``gemini flash: gemini-3.8-flash, gemini-3.7-flash``."""
    for result in classes:
        label = "gemini" if result.publisher == "google" else "claude"
        if result.models:
            text = ", ".join(result.models)
            if result.reason:
                text += f" (then {_REASON_TEXT.get(result.reason, result.reason)})"
        else:
            text = _REASON_TEXT.get(result.reason or "", result.reason or "none")
        logger.info("%s %s: %s", label, result.cls, text)


def classes_signature(
    gemini_classes: Sequence[ClassSetting], anthropic_classes: Sequence[ClassSetting]
) -> str:
    """Canonical text of the class settings and stage allowlist, for the cache key."""

    def part(classes: Sequence[ClassSetting]) -> str:
        return ".".join(f"{c.name}{c.keep}" for c in classes)

    stages = ".".join(sorted(ALLOWED_STAGES))
    return f"g={part(gemini_classes)};a={part(anthropic_classes)};s={stages}"


def missing_fixed_models(fixed: Mapping[str, str], listed: Sequence[str]) -> list[tuple[str, str]]:
    """``(setting, id)`` for each fixed-purpose model the catalog no longer lists.

    Compares bare names (before ``@``), so a dated Claude id matches its listed name. An
    empty ``listed`` (the catalog was not read) reports nothing.
    """
    if not listed:
        return []
    bare = {m.split("@", 1)[0] for m in listed}
    return [(name, mid) for name, mid in fixed.items() if mid and mid.split("@", 1)[0] not in bare]


# --- clients and probes ------------------------------------------------------------------


def _make_gemini_client() -> Any | None:
    try:
        return vertex.genai_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini client unavailable for model discovery: %s", exc)
        return None


def _make_anthropic_client() -> Any | None:
    try:
        # No SDK retries: check_model owns the single 429 retry (a probe must stay fast).
        return vertex.anthropic_client(max_retries=0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Anthropic-on-Vertex client unavailable for model discovery: %s", exc)
        return None


# PERF-015: a probe that hangs must not hold up startup (readiness waits on discovery).
PROBE_TIMEOUT_S = 10
# A 429 is retried once after this many seconds before the class counts as "no quota".
_QUOTA_RETRY_S = 2

# The chat agent always sends function declarations, so the probe sends one too (R3).
_PING_NAME = "ping"
_PING_DESCRIPTION = "Health check."


def _call_gemini(client: Any, model_id: str) -> None:
    from google.genai import types

    client.models.generate_content(
        model=model_id,
        contents="hello",
        config=types.GenerateContentConfig(
            max_output_tokens=1,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(name=_PING_NAME, description=_PING_DESCRIPTION)
                    ]
                )
            ],
            http_options=types.HttpOptions(timeout=PROBE_TIMEOUT_S * 1000),
        ),
    )


def _call_anthropic(client: Any, model_id: str) -> None:
    client.messages.create(
        model=model_id,
        max_tokens=1,
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {
                "name": _PING_NAME,
                "description": _PING_DESCRIPTION,
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        timeout=PROBE_TIMEOUT_S,
    )


def _probe_gemini(client: Any, model_id: str) -> bool:
    try:
        _call_gemini(client, model_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Gemini model '%s' did not pass the probe: %s", model_id, exc)
        return False


def _probe_anthropic(client: Any, model_id: str) -> bool:
    try:
        _call_anthropic(client, model_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Anthropic model '%s' did not pass the probe: %s", model_id, exc)
        return False


def _http_status(exc: BaseException) -> int | None:
    """The HTTP status of a provider refusal: genai ``APIError.code``, anthropic ``status_code``."""
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover - genai is a hard dependency in practice
        genai_errors = None
    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None)
    try:
        import anthropic
    except ImportError:  # pragma: no cover - optional provider
        return None
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code
    return None


def _is_transient(exc: BaseException, status: int | None) -> bool:
    """A 5xx (504 DEADLINE_EXCEEDED included), a timeout or a dropped connection."""
    if status is not None:
        return status >= 500
    if isinstance(exc, TimeoutError):
        return True
    try:
        import httpx
    except ImportError:  # pragma: no cover - google-genai depends on httpx
        httpx = None
    if httpx is not None and isinstance(exc, httpx.TransportError):
        return True
    try:
        import anthropic
    except ImportError:  # pragma: no cover - optional provider
        return False
    return isinstance(exc, anthropic.APIConnectionError)


def check_model(call: Callable[[], object], model_id: str = "") -> ProbeOutcome:
    """Run one probe call and classify the result (catalog path, research R3).

    A 429 is retried once after ``_QUOTA_RETRY_S``: still 429 means "this class has no
    quota". A transient error is retried once at once: the first call to a newly released
    model can take longer than the probe timeout while the second answers in ~2 s (live
    2026-10-19: gemini-3.8-flash took 14.8 s cold, then 504'd a 10 s probe at boot). A
    400 is not retried: it means the model rejects the request (e.g. no tool support).
    """
    for attempt in (1, 2):
        try:
            call()
            return ProbeOutcome.PASSED
        except Exception as exc:  # noqa: BLE001 - classified below
            status = _http_status(exc)
            if status in (403, 404):
                logger.debug("model '%s' is not enabled: %s", model_id, exc)
                return ProbeOutcome.NOT_ENABLED
            if status == 429:
                if attempt == 1:
                    time.sleep(_QUOTA_RETRY_S)
                    continue
                return ProbeOutcome.NO_QUOTA
            if attempt == 1 and _is_transient(exc, status):
                logger.info("model '%s' probe hit a transient error, retrying once: %s", model_id, exc)
                continue
            logger.info("model '%s' did not pass the probe: %s", model_id, exc)
            return ProbeOutcome.FAILED
    return ProbeOutcome.NO_QUOTA  # pragma: no cover - the loop always returns


# --- discovery -----------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _degraded(configured_default: str, fallback_models: list[str], **extra: Any) -> ModelCatalog:
    models = fallback_models or [configured_default]
    default = configured_default if configured_default in models else models[0]
    logger.warning("Model discovery degraded; serving fallback %s", models)
    return ModelCatalog(
        models=models, default=default, degraded=True, source="degraded", fetched_at=_now(), **extra
    )


def _discover_static(
    gemini_ids: list[str], anthropic_ids: list[str], configured_default: str, fallback_models: list[str]
) -> ModelCatalog:
    """Probe the configured ids and keep the ones that answer, in configured order."""
    infra_ran = False
    # PERF-015: probe every candidate concurrently instead of one after another; results
    # keep the configured order (Gemini first, then Anthropic).
    probes: list[tuple[str, Any]] = []

    if gemini_ids:
        gclient = _make_gemini_client()
        if gclient is not None:
            infra_ran = True
            probes += [(m, lambda m=m: _probe_gemini(gclient, m)) for m in gemini_ids]

    if anthropic_ids:
        aclient = _make_anthropic_client()
        if aclient is not None:
            infra_ran = True
            probes += [(m, lambda m=m: _probe_anthropic(aclient, m)) for m in anthropic_ids]

    results = _gather_threads([probe for _, probe in probes], max_workers=8)
    validated = [m for (m, _), ok in zip(probes, results) if ok is True]

    if not infra_ran or not validated:
        logger.warning("No model passed its probe (infra_ran=%s)", infra_ran)
        return _degraded(configured_default, fallback_models)

    default = configured_default if configured_default in validated else validated[0]
    return ModelCatalog(
        models=validated, default=default, degraded=False, source="static", fetched_at=_now()
    )


def _list_catalog() -> list[CatalogEntry]:
    """Both publishers' listings, fetched concurrently. Either failing fails the listing:
    a half-catalog dropdown would hide models with no visible reason."""
    results = _gather_threads(
        [lambda p=p: vertex.list_publisher_models(p) for p in ("google", "anthropic")]
    )
    entries: list[CatalogEntry] = []
    for result in results:
        if isinstance(result, CatalogUnavailable):
            raise result
        if isinstance(result, BaseException):
            raise CatalogUnavailable(f"{type(result).__name__}: {result}") from result
        entries += result
    return entries


def _discover_catalog(
    entries: list[CatalogEntry],
    classes: Sequence[ClassSetting],
    configured_default: str,
    fallback_models: list[str],
) -> ModelCatalog:
    by_class = candidates_by_class(entries, classes)
    # Two spare versions per class cover a newest one that isn't enabled yet (R4).
    probed = {c: by_class[(c.publisher, c.name)][: c.keep + 2] for c in classes}
    clients: dict[str, Any] = {}
    if any(c.publisher == "google" and probed[c] for c in classes):
        clients["google"] = _make_gemini_client()
    if any(c.publisher == "anthropic" and probed[c] for c in classes):
        clients["anthropic"] = _make_anthropic_client()
    callers = {"google": _call_gemini, "anthropic": _call_anthropic}

    ids: list[str] = []
    calls: list[Callable[[], ProbeOutcome]] = []
    for setting, candidates in probed.items():
        client = clients.get(setting.publisher)
        if client is None:
            continue  # no outcome: pick_per_class counts it as failed
        caller = callers[setting.publisher]
        for c in candidates:
            if c.model_id in ids:
                continue
            ids.append(c.model_id)
            calls.append(
                lambda c=c, client=client, caller=caller: check_model(
                    lambda: caller(client, c.model_id), c.model_id
                )
            )
    # One wave for every class: a wave costs at most one probe timeout (SC-004).
    results = _gather_threads(calls, max_workers=32)
    outcomes = {
        mid: r if isinstance(r, ProbeOutcome) else ProbeOutcome.FAILED for mid, r in zip(ids, results)
    }

    picked = [pick_per_class(c, probed[c], outcomes) for c in classes]
    log_class_results(picked)
    listed = sorted({callable_id(e) for e in entries} | {e.name for e in entries})
    models = list(dict.fromkeys(m for result in picked for m in result.models))
    if not models:
        return _degraded(configured_default, fallback_models, classes=picked, listed=listed)
    return ModelCatalog(
        models=models,
        default=choose_default(models, configured_default, picked),
        degraded=False,
        source="catalog",
        classes=picked,
        listed=listed,
        fetched_at=_now(),
    )


def discover_models(
    *,
    mode: Literal["catalog", "static"] = "static",
    gemini_ids: list[str],
    anthropic_ids: list[str],
    configured_default: str,
    fallback_models: list[str],
    gemini_classes: Sequence[ClassSetting] = (),
    anthropic_classes: Sequence[ClassSetting] = (),
) -> ModelCatalog:
    """The selectable models, their default, and where they came from (``source``).

    - ``models``: the ids that passed their probe, in serving order; never empty.
    - ``default``: ``configured_default`` if it passed, else the newest flash (catalog) or
      the first validated id (static).
    - ``degraded``: True when probing couldn't run (or found nothing) and the fallback set
      is being served instead.
    """
    if mode == "catalog" and not vertex.uses_vertex():
        logger.info("model catalog needs Vertex (GOOGLE_GENAI_USE_VERTEXAI); probing the static lists")
        mode = "static"
    if mode != "catalog":
        return _discover_static(gemini_ids, anthropic_ids, configured_default, fallback_models)
    try:
        entries = _list_catalog()
    except CatalogUnavailable as exc:
        logger.warning("model catalog unavailable (%s); probing the static lists", exc)
        result = _discover_static(gemini_ids, anthropic_ids, configured_default, fallback_models)
        return result if result.degraded else result.model_copy(update={"source": "fallback"})
    return _discover_catalog(
        entries, [*gemini_classes, *anthropic_classes], configured_default, fallback_models
    )
