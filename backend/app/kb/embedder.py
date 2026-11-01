"""Text embeddings for the knowledge base (feature 043, contract 2).

``Embedder`` is the seam: the background indexer embeds chunks with ``RETRIEVAL_DOCUMENT``,
044's search embeds queries with ``RETRIEVAL_QUERY``. Both ask :func:`get_embedder`, which is
``None`` when embeddings are unavailable (chunks then stay keyword-searchable). Tests inject a
fake with :func:`set_embedder`; CI never calls Vertex. The Vertex implementation
(``gemini-embedding-001`` through the provider layer) arrives with sc-112.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal, Protocol

from ..db.models import KB_DIMENSIONS

EmbedTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
DIMENSIONS = KB_DIMENSIONS


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        """One unit-norm ``DIMENSIONS``-d vector per text, in order. Raises on failure."""
        ...


def normalise(vector: Sequence[float]) -> list[float]:
    """``vector`` scaled to unit L2 length; a zero vector comes back unchanged."""
    norm = math.sqrt(math.fsum(v * v for v in vector))
    return [float(v) / norm for v in vector] if norm else [float(v) for v in vector]


_injected: Embedder | None = None


def set_embedder(embedder: Embedder | None) -> None:
    """Test injection point: :func:`get_embedder` returns ``embedder`` until cleared (None)."""
    global _injected
    _injected = embedder


def get_embedder() -> Embedder | None:
    """The injected embedder, else ``None`` (embeddings unavailable). Never raises."""
    return _injected
