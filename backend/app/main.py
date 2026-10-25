"""FastAPI application: lifespan (DB init), CORS, routers, health."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.sessions import DatabaseSessionService
from sqlalchemy import text

from wcl_agent.cache.cache import CacheFamily, family_ttl, get_or_load, keys
from wcl_agent.cache.cache_models import ModelCatalog
from wcl_agent.llm.genai_compat import ensure_genai_serializers_built
from wcl_agent.guides.guide_meta import set_brief_loader
from wcl_agent.llm.models import (
    choose_default,
    classes_signature,
    discover_models,
    has_transient_gaps,
    is_catalog_id,
    log_class_results,
    missing_fixed_models,
)
from wcl_agent.llm.vertex import model_location, project_id
from wcl_agent.client.wcl_client import aclose_clients

from .agent_runner import set_session_service
from .api import (
    admin_guides,
    admin_users,
    cache_stats,
    auth,
    conversations,
    greeting,
    guides,
    models,
    profile,
    raids,
    recent_raids,
    reports,
    ws,
)
from .api.errors import install_error_handlers
from .auth.redaction import RedactionFilter
from .config import settings

logger = logging.getLogger(__name__)


def _install_log_redaction() -> None:
    """Attach the redaction filter to the root logger + its handlers (feature 006, FR-030).

    Defense in depth so structured ``extra``/args can't leak secrets into logs/APM. Messages
    are not meant to carry secrets by construction; auditing still uses the dedicated writer.
    """
    f = RedactionFilter()
    root = logging.getLogger()
    root.addFilter(f)
    for handler in root.handlers:
        handler.addFilter(f)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(f)


def _install_app_logging() -> None:
    """Make the app's own INFO lines visible under uvicorn (feature 011, FR-013).

    uvicorn configures only its own loggers; the root logger has no handler, so INFO
    records from ``backend.app.*`` / ``wcl_agent.*`` (per-turn ``turn stats``, boot steps,
    round-cap notices) were silently dropped. Attach one root handler (if none) and set
    just the app namespaces to INFO — third-party libraries keep their defaults.
    """
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        root.addHandler(handler)
    for name in ("backend.app", "wcl_agent"):
        logging.getLogger(name).setLevel(logging.INFO)


_install_app_logging()
_install_log_redaction()  # after: the redaction filter attaches to the handler above too
from .db.session import engine
from .greeting import GREETING_MODEL, get_greeting
from .services.guide import load_brief_record, maybe_scan_stale_guides, touch_guide_wanted
from .startup import ReadinessGate, StartupTracker


def _brief_used(record) -> None:
    """A tool handed this brief to the agent: the guide is in use (FR-051)."""
    touch_guide_wanted([(record.class_name, record.spec, record.content_type)])


# A catalog result that lost a model to a likely transient error is kept this long only,
# so one bad probe at boot doesn't hide a model or class for the full 6 h (QA BUG-005).
_UNSETTLED_CATALOG_TTL_S = 600


def _catalog_ttl(catalog: ModelCatalog) -> int:
    """Only a real catalog result is shared: a fallback or degraded one is retried next boot."""
    if catalog.source != "catalog" or catalog.degraded:
        return 0
    ttl = family_ttl(CacheFamily.MODEL_CATALOG)
    return min(ttl, _UNSETTLED_CATALOG_TTL_S) if has_transient_gaps(catalog.classes) else ttl


async def _load_models(app: FastAPI) -> tuple[ModelCatalog, bool]:
    """Discover the selectable models into ``app.state``; returns (result, from cache).

    US4: blocking probes run off the event loop. app.state is the single runtime source
    of truth for the set and the default (see model_state.get_model_state); never left
    empty (FR-016). Feature 016: in catalog mode the result is shared through the
    model_catalog cache family, so restarts and other workers skip the listing and the
    probes; every boot still logs the per-class picks and the fixed-model warnings.
    """
    mode = settings.model_discovery_mode
    gemini_classes = settings.gemini_classes
    anthropic_classes = settings.anthropic_classes
    loaded = False

    async def load() -> ModelCatalog:
        nonlocal loaded
        loaded = True
        return await asyncio.to_thread(
            discover_models,
            mode=mode,
            gemini_ids=settings.gemini_models,
            anthropic_ids=settings.anthropic_models,
            configured_default=settings.default_model,
            fallback_models=settings.model_list,
            gemini_classes=gemini_classes,
            anthropic_classes=anthropic_classes,
        )

    if mode == "catalog":
        project = await asyncio.to_thread(project_id)
        key = keys.model_catalog(
            project or "-",
            model_location(),
            classes_signature(gemini_classes, anthropic_classes),
        )
        catalog = await get_or_load(
            CacheFamily.MODEL_CATALOG, key, ModelCatalog, load, ttl=_catalog_ttl
        )
        if not loaded and not all(is_catalog_id(m) for m in catalog.models):
            # A stored value is only trusted in the shape discovery itself serves (QA SEC-002).
            logger.warning("cached model catalog holds unexpected ids %s; rediscovering", catalog.models)
            catalog = await get_or_load(
                CacheFamily.MODEL_CATALOG, key, ModelCatalog, load, ttl=_catalog_ttl, force_refresh=True
            )
        # The default follows the current WCL_DEFAULT_MODEL, not the one of the boot that
        # stored the value (QA BUG-004).
        default = choose_default(catalog.models, settings.default_model, catalog.classes)
        if catalog.source == "catalog" and default != catalog.default:
            catalog = catalog.model_copy(update={"default": default})
    else:
        catalog = await load()
    if not loaded:
        log_class_results(catalog.classes)  # every boot explains its picks (SC-006)
    fixed = {
        "WCL_GUIDE_MODEL": settings.wcl_guide_model,
        "WCL_GUIDE_REVIEW_MODEL": settings.wcl_guide_review_model,
        "WCL_REPORT_MODEL": settings.wcl_report_model,
        "greeting": GREETING_MODEL,
    }
    for name, model in missing_fixed_models(fixed, catalog.listed):
        logger.warning("%s=%s is not in the model catalog; it may be retired", name, model)
    app.state.models = catalog.models
    app.state.default_model = catalog.default
    app.state.models_degraded = catalog.degraded
    return catalog, not loaded


async def _boot(app: FastAPI, tracker: StartupTracker) -> None:
    """The boot sequence, run as a background task so the port opens immediately.

    Every step reports into ``tracker`` (surfaced by /api/health for the frontend's boot
    overlay). ``ReadinessGate`` keeps all non-health traffic out until ``tracker.finish()``,
    so nothing below needs to worry about requests observing half-initialised state.
    """
    try:
        # Eagerly build google-genai model serializers (they default to defer_build=True)
        # so ADK can serialize genai types nested in EventActions.state_delta during
        # parallel tool calls (the still-deferred "MockValSer" serializer would otherwise
        # crash the turn). Idempotent.
        async def _serializers() -> None:
            ensure_genai_serializers_built()

        await tracker.run("serializers", _serializers)

        # feature 006: Alembic is the schema authority — run `alembic upgrade head` before
        # starting (see quickstart.md). The app no longer creates/alters its own tables
        # (the old create_all + idempotent ALTER block was removed); create_all survives
        # only in the SQLite test fixtures. ADK still owns its own session tables below.

        # Durable ADK sessions on the same database (US2): conversation context now
        # survives a restart. Reuses the app's async engine (ADK won't dispose it).
        async def _sessions() -> None:
            session_service = DatabaseSessionService(db_engine=engine)
            await session_service.prepare_tables()
            set_session_service(session_service)
            app.state.session_service = session_service

        await tracker.run("sessions", _sessions)

        # Feature 015 / US3: load the live class/spec roster from Warcraft Logs game data
        # (cached 24 h). Optional: without it the static fallback roster is used.
        async def _roster():
            from wcl_agent.game.roster import load_roster

            return await load_roster()

        await tracker.run(
            "roster",
            _roster,
            optional=True,
            detail=lambda r: f"{len(r.specs)} specs ({r.source})",
        )

        # Feature 015 / US2: tools read published coaching briefs through this loader
        # (replaces the boot-time cooldown registry; nothing to warm up).
        async def _guides() -> None:
            set_brief_loader(load_brief_record, on_used=_brief_used)
            maybe_scan_stale_guides()  # patch / season / hotfix changes since the last run

        await tracker.run("guides", _guides, optional=True, detail=lambda _: "brief loader ready")
        if settings.wcl_guide_review_model == settings.wcl_guide_model:
            # FR-046: the reviewer must be a different, stronger model than the author.
            logger.warning(
                "WCL_GUIDE_REVIEW_MODEL equals WCL_GUIDE_MODEL (%s): guides are reviewed by "
                "their own author model; set a different, stronger reviewer.",
                settings.wcl_guide_model,
            )

        await tracker.run(
            "models",
            lambda: _load_models(app),
            detail=lambda r: f"{len(r[0].models)} models ({r[0].source}"
            + (", cached)" if r[1] else ")"),
        )

        # US5: prime the fixed greeting model at startup, without blocking it. get_greeting
        # swallows its own failures, so a background task is safe (kept referenced so it
        # isn't garbage-collected before it runs). The endpoint awaits this task on a miss
        # rather than regenerating, so a fast model id makes greetings effectively instant.
        async def _greeting() -> None:
            app.state.greeting_cache = {}
            app.state.greeting_prime_task = asyncio.create_task(
                get_greeting(app, GREETING_MODEL)
            )

        await tracker.run("greeting", _greeting, detail=lambda _: "continues in background")

        tracker.finish()
        logger.info("Backend ready in %d ms", tracker.snapshot()["elapsed_ms"])
        # Feature 013 (SC-008): move the startup heap (ADK, genai, pydantic models…) out of
        # the cyclic GC's reach. Otherwise each collection triggered by parsing a large WCL
        # payload walks it, measured at ~80 ms of event-loop stall; frozen, ~3 ms.
        gc.collect()
        gc.freeze()
    except Exception:  # noqa: BLE001
        # Already recorded on the tracker (phase=failed) and logged by tracker.run; the
        # process stays up so /api/health can show *what* failed instead of a dead port.
        logger.error("Backend startup failed: %s", tracker.error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tracker = StartupTracker()
    app.state.startup = tracker
    boot_task = asyncio.create_task(_boot(app, tracker))
    app.state.boot_task = boot_task

    yield

    if not boot_task.done():
        boot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await boot_task
    with contextlib.suppress(Exception):
        await aclose_clients()  # WCL HTTP pools (feature 013)
    await engine.dispose()


app = FastAPI(title="WCL Agent Chat API", lifespan=lifespan)

# Added before CORS so CORS wraps it (last add_middleware = outermost): the 503s the
# gate emits during boot still carry CORS headers.
app.add_middleware(ReadinessGate)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_error_handlers(app)

app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(admin_guides.router)
app.include_router(cache_stats.router)
app.include_router(models.router)
app.include_router(conversations.router)
app.include_router(profile.router)
app.include_router(guides.router)
app.include_router(raids.router)
app.include_router(recent_raids.router)
app.include_router(reports.router)
app.include_router(greeting.router)
app.include_router(ws.router)


async def _db_ping() -> str:
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return "error"
    return "ok"


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    """Liveness + readiness. Reachable throughout boot (see ReadinessGate).

    ``status`` is ``booting`` until every startup step finished, then ``ok`` (or ``error``
    if a required step failed). ``startup`` carries the per-step progress the frontend's
    boot overlay renders. Without a tracker (tests, no lifespan) it reports ready.
    """
    tracker = getattr(app.state, "startup", None)
    startup = tracker.snapshot() if isinstance(tracker, StartupTracker) else None
    if startup is None or startup["ready"]:
        status = "ok"
    elif startup["phase"] == "failed":
        status = "error"
    else:
        status = "booting"
    return {"status": status, "db": await _db_ping(), "startup": startup}
