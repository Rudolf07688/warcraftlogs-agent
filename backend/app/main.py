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

from wcl_agent.genai_compat import ensure_genai_serializers_built
from wcl_agent.models import discover_models
from wcl_agent.wcl_client import aclose_clients

from .agent_runner import set_session_service
from .api import (
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
from .services.guide import load_guide_registry
from .startup import ReadinessGate, StartupTracker


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

        # Feature 009 / US5: publish ready spec guides' patch + major cooldowns to the
        # in-process wcl_agent registry (consumed by get_cooldown_usage). Best-effort —
        # an empty or unreachable table must not block startup (optional step).
        async def _guides() -> int:
            loaded = await load_guide_registry()
            logger.info("Guide registry loaded: %d ready guides", loaded)
            return loaded

        await tracker.run(
            "guides", _guides, optional=True, detail=lambda n: f"{n} ready guides"
        )

        # US4: discover + validate the selectable models once (blocking probes off the
        # event loop). app.state is the single runtime source of truth for the set and
        # the default (see model_state.get_model_state); never left empty (FR-016).
        async def _models() -> dict:
            discovery = await asyncio.to_thread(
                discover_models,
                gemini_ids=settings.gemini_models,
                anthropic_ids=settings.anthropic_models,
                configured_default=settings.default_model,
                fallback_models=settings.model_list,
            )
            app.state.models = discovery["models"]
            app.state.default_model = discovery["default"]
            app.state.models_degraded = discovery["degraded"]
            return discovery

        await tracker.run(
            "models",
            _models,
            detail=lambda d: f"{len(d['models'])} models"
            + (" (degraded)" if d["degraded"] else ""),
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
