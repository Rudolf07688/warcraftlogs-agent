"""The knowledge search eval: load the fixture corpus, run every question per mode, score.

Recall@k counts the labelled sources among the top k hits; latency is the wall time of one
``search`` call. The corpus is loaded into a Postgres database the caller owns (a throwaway
container or ``TEST_DATABASE_URL``), through the same tables and visibility rule the app uses.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus.json"
QUESTIONS = ROOT / "questions.json"
EMBEDDINGS = ROOT / "embeddings.json"
REAL_PREFIX = "vertex:"  # an embeddings set recorded with the real embedder
MODES = ("hybrid", "vector", "keyword")


def load_corpus() -> dict[str, list[dict[str, Any]]]:
    return json.loads(CORPUS.read_text())


def load_questions() -> list[dict[str, Any]]:
    return json.loads(QUESTIONS.read_text())


def chunk_ids(corpus: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {chunk["id"] for chunks in corpus.values() for chunk in chunks}


def recall_at_k(expected: Sequence[str], got: Sequence[str], k: int) -> float:
    """Share of the expected ids found in the first ``k`` results."""
    if not expected:
        return 1.0
    return len(set(expected) & set(got[:k])) / len(set(expected))


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (``p`` in 0-100); 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def is_real(set_name: str) -> bool:
    return set_name.startswith(REAL_PREFIX)


# --- The run (Postgres) --------------------------------------------------------------------


def load_embeddings() -> tuple[str, dict[str, list[float]]]:
    """The recorded set (``record`` writes it), else the deterministic stand-in."""
    if EMBEDDINGS.exists():
        data = json.loads(EMBEDDINGS.read_text())
        return data["set"], data["vectors"]
    from .standin import SET_NAME, embed_one

    corpus, questions = load_corpus(), load_questions()
    vectors = {c["id"]: embed_one(c["text"]) for chunks in corpus.values() for c in chunks}
    vectors.update({q["id"]: embed_one(q["question"]) for q in questions})
    return SET_NAME, vectors


class RecordedEmbedder:
    """Serves the recorded question vectors (by question text), like the real query embedder."""

    def __init__(self, set_name: str, by_text: dict[str, list[float]]):
        self.model = set_name
        self._by_text = by_text

    async def embed(self, texts: Sequence[str], *, task: str) -> list[list[float]]:
        return [self._by_text[t] for t in texts]


_REPORT_QUERY = "query EvalReport($code: String!) { reportData { report(code: $code) { code } } }"
_CONTENT_TYPES = {"raid": "ev-raid", "mplus": "ev-mplus"}  # spec_guides is unique per type


async def seed(maker, vectors: dict[str, list[float]]) -> tuple[Any, dict[tuple, str]]:
    """Load the corpus as public WCL fetches, eval guides and one workspace's chats.

    Returns the workspace id and a map from each hit's source pointer to its corpus id.
    Re-running replaces the eval guides' chunks; WCL fetches and the workspace are new each run.
    """
    import hashlib
    import uuid
    from datetime import UTC, datetime

    from sqlalchemy import delete, select

    from backend.app.db.models import Conversation, KbChatChunk, KbChunk, SpecGuide
    from backend.app.repositories import tenants as tenants_repo
    from backend.app.repositories.raw_fetches import ReportStatus, record_report_status, upsert_raw_fetch
    from backend.app.services.name_resolver import name_key
    from backend.app.tenancy.context import set_scope
    from wcl_agent.client.wcl_client import FetchedResponse

    corpus = load_corpus()
    now = datetime.now(UTC)
    run = uuid.uuid4().hex[:6]
    pointers: dict[tuple, str] = {}
    async with maker() as db:
        tenant = await tenants_repo.create_tenant(db, name=f"kb-eval-{run}")
        fetch_keys: dict[str, str] = {}
        for chunk in corpus["wcl"]:
            code = chunk["report_code"]
            if code not in fetch_keys:
                variables = {"code": code}
                key = hashlib.sha256(f"{run}:{code}".encode()).hexdigest()
                await upsert_raw_fetch(db, FetchedResponse(key, _REPORT_QUERY, variables, b'{"data": {}}', now))
                fetch_keys[code] = key
        await record_report_status(db, [ReportStatus(code, "public", None, now) for code in fetch_keys])
        for chunk in corpus["wcl"]:
            players = [{**p, "key": name_key(p["name"])} for p in chunk.get("players", [])]
            db.add(KbChunk(
                kind="wcl", raw_fetch_id=fetch_keys[chunk["report_code"]], chunk_key=chunk["id"],
                label=chunk["label"], text=chunk["text"], content_hash=chunk["id"],
                embedding=vectors[chunk["id"]], report_code=chunk["report_code"],
                fight_id=chunk["fight_id"], encounter_id=chunk.get("encounter_id"),
                difficulty=chunk.get("difficulty"), kill=chunk.get("kill"),
                start_time=datetime.fromisoformat(chunk["start_time"]), players=players,
                class_name=chunk.get("class_name"), spec=chunk.get("spec"),
            ))
            pointers[("wcl", chunk["report_code"], chunk["fight_id"], chunk["label"])] = chunk["id"]
        for chunk in corpus["guide"]:
            content_type = _CONTENT_TYPES[chunk["content_type"]]
            guide = await db.scalar(select(SpecGuide).where(
                SpecGuide.class_name == chunk["class_name"], SpecGuide.spec == chunk["spec"],
                SpecGuide.content_type == content_type,
            ))
            if guide is None:
                guide = SpecGuide(class_name=chunk["class_name"], spec=chunk["spec"], content_type=content_type)
                db.add(guide)
                await db.flush()
            await db.execute(delete(KbChunk).where(KbChunk.guide_id == guide.id, KbChunk.chunk_key == chunk["id"]))
            db.add(KbChunk(
                kind="guide", guide_id=guide.id, chunk_key=chunk["id"], label=chunk["section"],
                text=chunk["text"], content_hash=chunk["id"], embedding=vectors[chunk["id"]],
                class_name=chunk["class_name"], spec=chunk["spec"], content_type=content_type,
                section=chunk["section"],
            ))
            pointers[("guide", chunk["class_name"], chunk["spec"], content_type, chunk["section"])] = chunk["id"]
        await db.commit()
    async with maker() as db:
        await set_scope(db, tenant_id=tenant.id)
        conversations: dict[str, Any] = {}
        for chunk in corpus["chat"]:
            if chunk["conversation"] not in conversations:
                conv = Conversation(tenant_id=tenant.id, model="eval")
                db.add(conv)
                await db.flush()
                conversations[chunk["conversation"]] = conv.id
            conv_id = conversations[chunk["conversation"]]
            db.add(KbChatChunk(
                tenant_id=tenant.id, conversation_id=conv_id, message_seq=chunk["message_seq"],
                created_at=datetime.fromisoformat(chunk["created_at"]), label=chunk["id"],
                text=chunk["text"], content_hash=chunk["id"], embedding=vectors[chunk["id"]],
                characters=[{"name": c, "key": name_key(c)} for c in chunk["characters"]],
            ))
            pointers[("chat", str(conv_id), chunk["message_seq"])] = chunk["id"]
        await db.commit()
    return tenant.id, pointers


def _pointer(hit) -> tuple:
    s = hit.source
    if hit.kind == "wcl":
        return ("wcl", s["report_code"], s["fight_id"], s["label"])
    if hit.kind == "guide":
        return ("guide", s["class_name"], s["spec"], s["content_type"], s["section"])
    return ("chat", s["conversation_id"], s["message_seq"])


async def run(maker, *, k: int = 8) -> dict[str, Any]:
    """Seed the corpus, ask every question in every mode, report recall@k and latency.

    Only eval sources count, in the order they ranked: other rows already in the database are
    skipped, so use a fresh database for numbers worth comparing (quickstart.md). It seeds fake
    public reports and global guide chunks: never the app's database (the CLI refuses it).
    """
    import time

    from backend.app.kb import search as kb

    set_name, vectors = load_embeddings()
    questions = load_questions()
    tenant_id, pointers = await seed(maker, vectors)
    embedder = RecordedEmbedder(set_name, {q["question"]: vectors[q["id"]] for q in questions})
    report: dict[str, Any] = {"set": set_name, "k": k, "questions": len(questions), "modes": {}}
    for mode in MODES:
        recalls, latencies = [], []
        for q in questions:
            request = kb.SearchRequest((q["question"],), kb.SearchFilters(), frozenset(), kb.MAX_K, tenant_id)
            started = time.perf_counter()
            result = await kb.search(request, embedder=embedder, mode=mode)
            latencies.append((time.perf_counter() - started) * 1000)
            got = [pointers[p] for p in map(_pointer, result.hits) if p in pointers]
            recalls.append(recall_at_k(q["expected"], got, k))
        report["modes"][mode] = {
            "recall": round(sum(recalls) / len(recalls), 3),
            "p50_ms": round(percentile(latencies, 50), 1),
            "p95_ms": round(percentile(latencies, 95), 1),
        }
    return report
