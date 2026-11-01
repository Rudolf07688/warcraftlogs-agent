"""``python -m backend.evals.kb`` — the knowledge search eval (feature 044, sc-115).

    run [--k 8]                     recall@k per mode + latency on DATABASE_URL (a fresh DB is best)
    record [--max-texts 300]        team-lead: embed corpus + questions with the real embedder
    live [--max-questions 30] [--model M]   team-lead: filter accuracy + local-answer rate

``run`` needs a migrated Postgres with pgvector. ``record`` and ``live`` call live services and
are never part of the pytest run.
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
    run.add_argument("--k", type=int, default=8)
    rec = sub.add_parser("record", help="embed the corpus and questions with the real embedder")
    rec.add_argument("--max-texts", type=int, default=300)
    live = sub.add_parser("live", help="filter-extraction accuracy and local-answer rate")
    live.add_argument("--max-questions", type=int, default=30)
    live.add_argument("--model", default=None)
    return p


async def _main(args: argparse.Namespace) -> int:
    from backend.app.db import session as db_session

    if args.cmd == "run":
        from .harness import run

        print(json.dumps(await run(db_session.SessionLocal, k=args.k), indent=1))
        return 0
    from . import live

    if args.cmd == "record":
        return await live.record(max_texts=args.max_texts)
    return await live.live(db_session.SessionLocal, max_questions=args.max_questions, model=args.model)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parser().parse_args())))
