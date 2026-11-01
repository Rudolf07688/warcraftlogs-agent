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
