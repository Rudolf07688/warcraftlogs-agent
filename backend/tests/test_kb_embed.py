"""The knowledge base embedder contract (feature 043, contract 2). No Vertex call: tests inject
fakes through ``set_embedder``."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from backend.app.kb.embedder import get_embedder, normalise, set_embedder


@pytest.fixture(autouse=True)
def _clean():
    set_embedder(None)
    yield
    set_embedder(None)


def test_normalise_gives_unit_length_and_keeps_zero():
    assert normalise([3.0, 4.0]) == [0.6, 0.8]
    assert math.isclose(math.fsum(v * v for v in normalise([1.0, 2.0, 2.0])), 1.0)
    assert normalise([0.0, 0.0]) == [0.0, 0.0]


def test_get_embedder_is_none_until_one_is_available():
    assert get_embedder() is None


def test_get_embedder_returns_the_injected_one_until_cleared():
    fake = SimpleNamespace(model="fake")
    set_embedder(fake)
    assert get_embedder() is fake
    set_embedder(None)
    assert get_embedder() is None
