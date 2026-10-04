"""FastAPI application: lifespan (DB init), CORS, routers, health."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.sessions import DatabaseSessionService
from sqlalchemy import text

from wcl_agent.genai_compat import ensure_genai_serializers_built
from wcl_agent.models import discover_models

from .agent_runner import set_session_service
from .api import (
    admin_users,
    auth,
    conversations,
    greeting,
    guides,
    models,
    profile,
    raids,
    reports,
    ws,
)
from .api.errors import install_error_handlers
from .auth.redaction import RedactionFilter
from .config import settings


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


_install_log_redaction()
from .db.session import engine
from .greeting import GREETING_MODEL, get_greeting


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly build google-genai model serializers (they default to defer_build=True) so ADK
    # can serialize genai types nested in EventActions.state_delta during parallel tool calls
    # (the still-deferred "MockValSer" serializer would otherwise crash the turn). Idempotent.
    ensure_genai_serializers_built()

    # feature 006: Alembic is the schema authority — run `alembic upgrade head` before
    # starting (see quickstart.md). The app no longer creates/alters its own tables
    # (the old create_all + idempotent ALTER block was removed); create_all survives
    # only in the SQLite test fixtures. ADK still owns its own session tables below.

    # Durable ADK sessions on the same database (US2): conversation context now
    # survives a restart. Reuses the app's async engine (ADK won't dispose it).
    session_service = DatabaseSessionService(db_engine=engine)
    await session_service.prepare_tables()
    set_session_service(session_service)
    app.state.session_service = session_service

    # US4: discover + validate the selectable models once (blocking probes off the
    # event loop). app.state is the single runtime source of truth for the set and
    # the default (see model_state.get_model_state); never left empty (FR-016).
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

    # US5: prime the fixed greeting model at startup, without blocking it. get_greeting
    # swallows its own failures, so a background task is safe (kept referenced so it
    # isn't garbage-collected before it runs). The endpoint awaits this task on a miss
    # rather than regenerating, so a fast model id makes greetings effectively instant.
    app.state.greeting_cache = {}
    app.state.greeting_prime_task = asyncio.create_task(get_greeting(app, GREETING_MODEL))

    yield
    await engine.dispose()


app = FastAPI(title="WCL Agent Chat API", lifespan=lifespan)

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
app.include_router(models.router)
app.include_router(conversations.router)
app.include_router(profile.router)
app.include_router(guides.router)
app.include_router(raids.router)
app.include_router(reports.router)
app.include_router(greeting.router)
app.include_router(ws.router)


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    return {"status": "ok", "db": db_status}
