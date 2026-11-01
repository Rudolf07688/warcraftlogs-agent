"""A deterministic stand-in embedder for the eval when no recorded embeddings exist.

Hashed word and character-trigram features in 768 dimensions, unit-normalised. It proves the
harness and the SQL, not the embedding model: recall measured with it is only reported, never
asserted (Gate 1, board #37).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

DIMENSIONS = 768
SET_NAME = "stand-in"
_WORD = re.compile(r"\w+")


def _features(text: str) -> list[str]:
    words = _WORD.findall(text.casefold())
    grams = [w[i : i + 3] for w in words for i in range(max(1, len(w) - 2))]
    return words + grams


def embed_one(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for feature in _features(text):
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSIONS
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(math.fsum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


class StandInEmbedder:
    """The ``Embedder`` Protocol over :func:`embed_one` (the task type is ignored)."""

    model = SET_NAME

    async def embed(self, texts: Sequence[str], *, task: str) -> list[list[float]]:
        return [embed_one(t) for t in texts]
