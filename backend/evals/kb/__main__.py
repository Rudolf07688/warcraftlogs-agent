"""``python -m backend.evals.kb`` — the knowledge search eval (feature 044, sc-115).

    run --db URL [--k 8]                         recall@k per mode + latency
    record [--max-texts 300]                     team-lead: embed corpus + questions for real
    live --db URL [--max-questions 30] [--model M]   team-lead: filter accuracy + local-answer rate

``run`` and ``live`` seed fake public reports, global guide chunks and a workspace into the
database they are given, and never clean up: ``--db`` must name a throwaway eval database
(migrated, with pgvector) whose name, as the server reports it, starts with ``kbeval``; anything
else, or a database that cannot be reached, is refused (P7 SEC-005, SEC-006). ``record`` and
``live`` call live services and are never part of the pytest run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backend.evals.kb")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="recall@k hybrid vs vector-only vs keyword, and latency")
    run.add_argument("--db", required=True, help="a throwaway eval database URL (never the app's)")
    run.add_argument("--k", type=int, default=8)
    rec = sub.add_parser("record", help="embed the corpus and questions with the real embedder")
    rec.add_argument("--max-texts", type=int, default=300)
    live = sub.add_parser("live", help="filter-extraction accuracy and local-answer rate")
    live.add_argument("--db", required=True, help="a throwaway eval database URL (never the app's)")
    live.add_argument("--max-questions", type=int, default=30)
    live.add_argument("--model", default=None)
    return p


EVAL_DB_PREFIX = "kbeval"


def refuse_database(name: str | None) -> str | None:
    """Why a database called ``name`` may not be seeded, or None when it is an eval database.

    The name is the one the server reports for the open connection (``current_database()``),
    never the URL, which has many spellings of the same server (``localhost``, ``127.0.0.1``,
    ``::1``, a socket path). Only a database named ``kbeval...`` is accepted."""
    if name and name.startswith(EVAL_DB_PREFIX):
        return None
    return (
        f"--db reaches database {name or '(unknown: not reachable, or not Postgres)'}; the eval seeds fake data and never cleans up, so the database "
        f"must be a throwaway one named {EVAL_DB_PREFIX!r}... (CREATE DATABASE {EVAL_DB_PREFIX})."
    )


async def _connected_database(engine) -> str | None:
    """The database the engine really reaches; None when it cannot be told (fail closed)."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT current_database()"))).scalar_one_or_none()
    except Exception:  # noqa: BLE001 - unreachable or not Postgres: refuse
        return None


async def _main(args: argparse.Namespace) -> int:
    if args.cmd == "record":
        from . import live

        return await live.record(max_texts=args.max_texts)
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.db import session as db_session

    engine = create_async_engine(args.db, pool_pre_ping=True)
    reason = refuse_database(await _connected_database(engine))
    if reason:
        await engine.dispose()
        print(reason)
        return 2
    # search() opens its own sessions: point the app's factory at the eval database too.
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if args.cmd == "run":
            from .harness import run

            print(json.dumps(await run(db_session.SessionLocal, k=args.k), indent=1))
            return 0
        from . import live

        return await live.live(db_session.SessionLocal, max_questions=args.max_questions, model=args.model)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parser().parse_args())))
