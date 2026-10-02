"""FastAPI application: lifespan (DB init), CORS, routers, health."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.sessions import DatabaseSessionService
from sqlalchemy import text

from wcl_agent.models import discover_models

from .agent_runner import set_session_service
from .api import conversations, greeting, models, profile, raids, reports, ws
from .config import settings
from .db.models import Base
from .db.session import engine
from .greeting import GREETING_MODEL, get_greeting


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (simple v1; a migration tool is a later improvement).
    # Feature 005 adds three new tables (user_characters, guild_profile, artifacts) —
    # create_all picks them up additively (new tables only; no ALTER needed).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all adds new *tables* only — it does NOT alter the pre-existing
        # `messages` table from feature 001. Add the US2 `status` column with an
        # idempotent statement (Postgres only; SQLite test DBs get it via create_all).
        if engine.dialect.name == "postgresql":
            await conn.execute(
                text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
                    "status VARCHAR(10) NOT NULL DEFAULT 'complete'"
                )
            )
            # US2/US4: distinct boss list per report (added idempotently; existing
            # rows read back as NULL and are coerced to [] at the API edge).
            await conn.execute(
                text(
                    "ALTER TABLE tracked_raids ADD COLUMN IF NOT EXISTS "
                    "encounters JSONB"
                )
            )

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

app.include_router(models.router)
app.include_router(conversations.router)
app.include_router(profile.router)
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
