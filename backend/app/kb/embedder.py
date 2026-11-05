"""Text embeddings for the knowledge base (feature 043, contract 2).

``Embedder`` is the seam: the background indexer embeds chunks with ``RETRIEVAL_DOCUMENT``,
044's search embeds queries with ``RETRIEVAL_QUERY``. Both ask :func:`get_embedder`, which is
``None`` when embeddings are unavailable (chunks then stay keyword-searchable). Tests inject a
fake with :func:`set_embedder`; CI never calls Vertex.

:class:`VertexEmbedder` runs ``settings.kb_embed_model`` (``gemini-embedding-001``) at 768
dimensions through the provider layer (``wcl_agent.llm.generation.embed_texts``: only it calls
model clients) and the shared rate-limit loop, and L2-normalises the vectors: truncated Gemini
embeddings aren't unit length.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import math
import time
from collections.abc import Sequence
from typing import Literal, Protocol

from wcl_agent.llm import generation
from wcl_agent.llm.model_retry import RetryPolicy

from ..config import settings
from ..db.models import KB_DIMENSIONS
from ..telemetry.metrics import record_embedding

logger = logging.getLogger(__name__)

EmbedTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
DIMENSIONS = KB_DIMENSIONS
_POLICY = RetryPolicy(attempts=4, initial_s=2.0, max_s=20.0, budget_s=60.0)
# sc-319: query requests in flight at once; a search sends at most 5 queries.
QUERY_CONCURRENCY = 5
_TASK_LABELS: dict[EmbedTask, str] = {"RETRIEVAL_DOCUMENT": "document", "RETRIEVAL_QUERY": "query"}


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        """One unit-norm ``DIMENSIONS``-d vector per text, in order. Raises on failure."""
        ...


def normalise(vector: Sequence[float]) -> list[float]:
    """``vector`` scaled to unit L2 length; a zero vector comes back unchanged."""
    norm = math.sqrt(math.fsum(v * v for v in vector))
    return [float(v) / norm for v in vector] if norm else [float(v) for v in vector]


class VertexEmbedder:
    """Gemini embeddings through the provider layer, ``request_batch`` texts per request, at
    ``location`` (empty or None: the model location)."""

    def __init__(self, model: str, *, request_batch: int = 1, location: str | None = None):
        self.model = model
        self._request_batch = max(1, request_batch)
        self._location = location

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        parts = [texts[i : i + self._request_batch] for i in range(0, len(texts), self._request_batch)]
        if task == "RETRIEVAL_QUERY":
            # sc-319: a player waits on query embeddings, so their requests go out together
            # (bounded). Documents stay one request after another: the background indexer's
            # load on the quota is unchanged.
            limit = asyncio.Semaphore(QUERY_CONCURRENCY)

            async def bounded(part: Sequence[str]) -> list[list[float]]:
                async with limit:
                    return await self._request(part, task)

            results = await asyncio.gather(*(bounded(part) for part in parts))
        else:
            results = [await self._request(part, task) for part in parts]
        return [vector for result in results for vector in result]

    async def _request(self, part: Sequence[str], task: EmbedTask) -> list[list[float]]:
        """One provider request: its texts' unit vectors, recorded once whatever the outcome."""
        started = time.monotonic()
        try:
            raw = await generation.embed_texts(
                self.model, part, task=task, dimensions=DIMENSIONS, policy=_POLICY, location=self._location
            )
        except BaseException as exc:
            # Feature 059: per provider request, a failed one too (with its error type). sc-503:
            # BaseException, so a request cancelled by search's timeout (CancelledError) records too.
            record_embedding(self.model, _TASK_LABELS[task], len(part), time.monotonic() - started, exc)
            raise
        record_embedding(self.model, _TASK_LABELS[task], len(part), time.monotonic() - started)
        if len(raw) != len(part):
            raise ValueError(f"embedder returned {len(raw)} vectors for {len(part)} texts")
        for values in raw:
            if len(values) != DIMENSIONS:
                raise ValueError(f"embedder returned {len(values)} dimensions, not {DIMENSIONS}")
        return [normalise(values) for values in raw]


_injected: Embedder | None = None


def set_embedder(embedder: Embedder | None) -> None:
    """Test injection point: :func:`get_embedder` returns ``embedder`` until cleared (None)."""
    global _injected
    _injected = embedder


@functools.cache
def _vertex_embedder() -> VertexEmbedder | None:
    if not generation.embeddings_available():
        logger.warning("knowledge base embeddings unavailable: no genai client; keyword search only")
        return None
    return VertexEmbedder(
        settings.kb_embed_model,
        request_batch=settings.kb_embed_request_batch,
        location=settings.kb_embed_location,
    )


def get_embedder() -> Embedder | None:
    """The injected embedder, else ``None`` when embeddings are off or unavailable, else the
    process's Vertex embedder. Never raises."""
    if _injected is not None:
        return _injected
    if not settings.kb_embed_enabled:
        return None
    return _vertex_embedder()
