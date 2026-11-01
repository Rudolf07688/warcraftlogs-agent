"""``python -m backend.evals.kb`` — the knowledge search eval (feature 044, sc-115).

    run --db URL [--k 8]                         recall@k per mode + latency
    record [--max-texts 300]                     team-lead: embed corpus + questions for real
    live --db URL [--max-questions 30] [--model M]   team-lead: filter accuracy + local-answer rate

``run`` and ``live`` seed fake public reports, global guide chunks and a workspace into the
database they are given, and never clean up: ``--db`` must name a throwaway eval database
(migrated, with pgvector), and is refused when it is the app's own ``DATABASE_URL`` or
``DATABASE_OWNER_URL`` (P7 SEC-005). ``record`` and ``live`` call live services and are never
part of the pytest run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy.engine import make_url


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


def _same_database(a: str, b: str) -> bool:
    """Same host, port and database, whatever the role or driver."""
    if not a or not b:
        return False
    x, y = make_url(a), make_url(b)
    return (x.host, x.port or 5432, x.database) == (y.host, y.port or 5432, y.database)


def refuse_app_database(url: str) -> str | None:
    """Why ``url`` may not be seeded, or None when it is a separate database."""
    from backend.app.config import settings

    if any(_same_database(url, app) for app in (settings.database_url, settings.database_owner_url)):
        return "--db is the app's own database; the eval seeds fake data there. Use a throwaway eval DB."
    return None


async def _main(args: argparse.Namespace) -> int:
    if args.cmd == "record":
        from . import live

        return await live.record(max_texts=args.max_texts)
    reason = refuse_app_database(args.db)
    if reason:
        print(reason)
        return 2
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.db import session as db_session

    engine = create_async_engine(args.db, pool_pre_ping=True)
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
