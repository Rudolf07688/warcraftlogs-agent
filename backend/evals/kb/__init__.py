"""Knowledge search eval (feature 044, sc-115): recall@k hybrid vs vector-only, and latency.

``python -m backend.evals.kb run`` scores the fixture corpus on a Postgres database; ``record``
and ``live`` are team-lead's live modes (real embedder, real chat model). See
specs/044-kb-search/quickstart.md.
"""
