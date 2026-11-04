"""LLM price table and its generated Mimir rules (feature 055, sc-410)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


generate = _load("pricing_generate", ROOT / "observability" / "pricing" / "generate.py")
teamstats = _load("teamstats", ROOT / ".claude" / "team" / "teamstats.py")
PRICING = yaml.safe_load((ROOT / "observability" / "pricing" / "pricing.yaml").read_text())


def test_cost_rules_are_generated_from_the_price_table() -> None:
    """A price change is a pricing.yaml commit plus the generated cost.yaml: never one alone."""
    assert generate.RULES.read_text() == generate.render(PRICING)


def test_price_rules_are_usd_per_token() -> None:
    rules = yaml.safe_load(generate.render(PRICING))["groups"][0]["rules"]
    prices = {(r["labels"]["gen_ai_request_model"], r["labels"]["gen_ai_token_type"]): r["expr"]
              for r in rules if r["record"] == "llm_price_usd_per_token"}
    for model, row in PRICING["models"].items():
        for token_type, usd_per_million in row.items():
            value = float(prices[(model, token_type)].removeprefix("vector(").removesuffix(")"))
            assert value == pytest.approx(usd_per_million / 1e6, rel=1e-6)
    # The cost rule comes after every price in the group (rules evaluate in order).
    assert rules[-1]["record"] == "genai:cost_usd:rate5m"


def test_a_claude_and_a_gemini_model_are_priced() -> None:
    models = PRICING["models"]
    assert any(m.startswith("claude-") for m in models) and any(m.startswith("gemini-") for m in models)
    for row in models.values():
        assert set(row) == {"input", "output"} and all(v > 0 for v in row.values())


def test_teamstats_seat_cost_uses_the_tables_price() -> None:
    assert teamstats.INPUT_USD_PER_M == PRICING["models"][teamstats.LIST_PRICE_MODEL]["input"]


def test_provider_default_models_have_a_price() -> None:
    """Every model the app picks by default (wcl_agent/llm/provider.py) has a price row."""
    from wcl_agent.llm.provider import ROLE_DEFAULTS  # noqa: PLC0415

    defaults = {m for per_role in ROLE_DEFAULTS.values() for m in per_role.values()}
    assert defaults and defaults <= set(PRICING["models"]), defaults - set(PRICING["models"])
