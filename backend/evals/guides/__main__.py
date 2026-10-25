"""``python -m backend.evals.guides`` — the guide and coaching accuracy check.

    run [--baseline] [--specs Mage/Fire,...] [--content raid,mplus] [--skip-coaching] [--live-generate]
    datasheet <Class>/<Spec> <raid|mplus>

Exit codes for ``run``: 0 gate passed, 1 gate failed, 2 run error (contracts/accuracy-check.md).
Maintainer-run: calls live models and Warcraft Logs, so it is not part of the pytest run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fixtures import ROOT, load_all
from .scoring import (
    EXIT_ERROR,
    GuideRecord,
    abstention_quality,
    cited_sources,
    claim_support,
    current_source_precision,
    deltas,
    exit_code,
    fact_totals,
    gate,
    leakage,
    patch_accuracy,
    score_facts,
    spec_coverage,
)

logger = logging.getLogger("backend.evals.guides")

REPORTS = ROOT / "reports"
BASELINE = REPORTS / "baseline.json"
LINK_SAMPLE = 50
LINK_TIMEOUT_S = 10.0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backend.evals.guides")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="score published guides and coaching")
    run.add_argument("--baseline", action="store_true", help="write reports/baseline.json")
    run.add_argument("--specs", default="", help="comma list of Class/Spec (default: all with facts)")
    run.add_argument("--content", default="raid,mplus")
    run.add_argument("--skip-coaching", action="store_true")
    run.add_argument("--live-generate", action="store_true", help="regenerate the selected guides first")
    ds = sub.add_parser("datasheet", help="print one data sheet")
    ds.add_argument("spec", help="<Class>/<Spec>")
    ds.add_argument("content_type", choices=["raid", "mplus"])
    return p


def _selected_specs(arg: str) -> set[tuple[str, str]] | None:
    if not arg:
        return None
    out = set()
    for item in arg.split(","):
        cls, _, spec = item.strip().partition("/")
        if cls and spec:
            out.add((cls, spec))
    return out


# --- inputs -----------------------------------------------------------------------------


async def _load_guides() -> list[GuideRecord]:
    from backend.app.db import repository as repo
    from backend.app.db import session as db_session

    async with db_session.SessionLocal() as session:
        rows = await repo.list_spec_guides(session, with_text=True)
    return [
        GuideRecord(
            class_name=r.class_name,
            spec=r.spec,
            # getattr: a pre-feature checkout (baseline run) has no feature-015 columns.
            content_type=getattr(r, "content_type", "raid"),
            status=r.status,
            markdown=r.guide_markdown,
            game_patch=r.game_patch,
            season=getattr(r, "season", None),
            sources=list(r.sources or []),
            claims=getattr(r, "claims", None),
            brief=getattr(r, "brief", None),
            evidence=getattr(r, "evidence", None),
        )
        for r in rows
    ]


_GAME_CLASSES = "query EvalGameClasses { gameData { classes { name slug specs { name slug } } } }"


async def _roster() -> list[tuple[str, str]]:
    """Every live spec, straight from Warcraft Logs game data — deliberately not through the
    app's own roster code, so spec coverage is measured against an independent truth."""
    from wcl_agent.client import wcl_client
    from wcl_agent.client.wcl_client import background_lane

    with background_lane():
        data = await wcl_client.get_async_client().query(_GAME_CLASSES)
    classes = ((data.get("data") or {}).get("gameData") or {}).get("classes") or []
    return [(c["slug"], s["slug"]) for c in classes for s in c.get("specs") or []]


async def _listed_specs() -> list[tuple[str, str]]:
    """The specs the library lists (what ``GET /api/guides`` shows)."""
    from backend.app.services.guide import build_guide_roster

    return [(it["class_name"], it["spec"]) for it in build_guide_roster([], None)]


async def _live() -> tuple[str | None, str | None]:
    from wcl_agent.game import patch
    from wcl_agent.client.wcl_client import background_lane

    with background_lane():
        live_patch = await patch.current_patch()
        # Absent on a pre-feature checkout (baseline run): no season known then.
        season = getattr(patch, "current_mplus_season", None)
        return live_patch, (await season() if season else None)


async def _link_health(sources: list[dict]) -> dict[str, Any]:
    import httpx

    uris = sorted({s["uri"] for s in sources if s.get("uri")})
    sample = random.sample(uris, LINK_SAMPLE) if len(uris) > LINK_SAMPLE else uris
    if not sample:
        return {"rate": None, "checked": 0, "broken": []}

    async def ok(client: httpx.AsyncClient, uri: str) -> bool:
        try:
            r = await client.head(uri)
            if r.status_code >= 400:
                r = await client.get(uri)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async with httpx.AsyncClient(timeout=LINK_TIMEOUT_S, follow_redirects=True) as client:
        results = await asyncio.gather(*(ok(client, u) for u in sample))
    broken = [u for u, good in zip(sample, results) if not good]
    return {"rate": sum(results) / len(sample), "checked": len(sample), "broken": broken}


async def _live_generate(keys: list[tuple[str, str, str]]) -> None:
    """Regenerate each selected guide through the pipeline and wait for every run."""
    from backend.app.services import background
    from backend.app.services.guide import ensure_guide

    for cls, spec, ct in keys:
        await ensure_guide(cls, spec, ct, force=True)
    while pending := [t for t in list(background._bg_tasks) if not t.done()]:
        await asyncio.gather(*pending, return_exceptions=True)


# --- run --------------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from backend.app.config import settings

    facts, adversarial_cases, coaching_cases = load_all()
    specs = _selected_specs(args.specs)
    content_types = {c.strip() for c in args.content.split(",") if c.strip()}

    def wanted(cls: str, spec: str, ct: str) -> bool:
        return ct in content_types and (specs is None or (cls, spec) in specs)

    facts = [f for f in facts if wanted(*f.key)]
    coaching_cases = [c for c in coaching_cases if wanted(c.class_name, c.spec, c.content_type)]

    if args.live_generate:
        keys = sorted({f.key for f in facts} | {(c.class_name, c.spec, c.content_type) for c in coaching_cases})
        await _live_generate(keys)

    live_patch, live_season = await _live()
    all_guides = await _load_guides()
    by_key = {g.key: g for g in all_guides}
    guides = [g for g in all_guides if wanted(*g.key)]

    fact_rows: list[dict] = []
    for f in facts:
        g = by_key.get(f.key)
        text = g.markdown if g and g.published else None
        for r in score_facts(text, g.unconfirmed if g else [], f.facts):
            fact_rows.append({"guide": "/".join(f.key), "guide_missing": text is None, **r})
    # A missing guide is a coverage gap, not an abstention: score only published guides.
    totals = fact_totals(r for r in fact_rows if not r["guide_missing"])

    sources = [s for g in guides if g.published for s in cited_sources(g)]
    support = claim_support(guides)
    roster = await _roster()

    from .adversarial import evaluate

    adversarial = [await evaluate(c) for c in adversarial_cases]

    coaching_runs: list[dict] = []
    coaching_summary: dict[str, Any] = {}
    if not args.skip_coaching and coaching_cases:
        from .coaching import install_brief_loader, run_case, summarize

        install_brief_loader()  # as the backend does at startup

        for case in coaching_cases:
            coaching_runs.append(await run_case(case, model=settings.wcl_default_model, guides=by_key))
        coaching_summary = summarize(coaching_runs)

    metrics: dict[str, Any] = {
        "patch_accuracy": patch_accuracy(guides, live_patch, live_season),
        "claim_support_rate": support["rate"],
        "claim_support": support,
        "leakage_rate": leakage(sources),
        "current_source_precision": current_source_precision(sources, live_patch),
        "spec_coverage": spec_coverage(roster, await _listed_specs()),
        "facts": totals,
        "abstention_quality": abstention_quality(totals),
        "source_link_health": (await _link_health(sources))["rate"],
        "wrong_content_brief_use": coaching_summary.get("wrong_content_brief_use"),
        "coaching": coaching_summary,
    }
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "live_patch": live_patch,
        "live_season": live_season,
        "selection": {"specs": args.specs or "all", "content": sorted(content_types)},
        "guide_model": settings.wcl_guide_model,
        "review_model": getattr(settings, "wcl_guide_review_model", None),
        "chat_model": settings.wcl_default_model,
        "metrics": metrics,
        "guides": [
            {"guide": "/".join(g.key), "status": g.status, "published": g.published,
             "game_patch": g.game_patch, "season": g.season, "claims": len(g.claims or [])}
            for g in guides
        ],
        "facts": fact_rows,
        "adversarial": adversarial,
        "coaching": coaching_runs,
    }
    passed, reasons = gate(report)
    report["gate"] = {"passed": passed, "reasons": reasons}
    baseline = None if args.baseline or not BASELINE.exists() else json.loads(BASELINE.read_text())
    report["baseline_delta"] = deltas(report, baseline)
    return report


def _markdown(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        f"# Guide accuracy check — {report['generated_at']}",
        "",
        f"Live patch **{report['live_patch']}**, season **{report['live_season']}**. "
        f"Gate: **{'PASSED' if report['gate']['passed'] else 'FAILED'}**.",
        "",
    ]
    for reason in report["gate"]["reasons"]:
        lines.append(f"- {reason}")
    lines += ["", "| Metric | Value | Δ vs baseline |", "|---|---|---|"]
    delta = report.get("baseline_delta") or {}
    for key in (
        "patch_accuracy", "claim_support_rate", "leakage_rate", "current_source_precision",
        "spec_coverage", "abstention_quality", "source_link_health", "wrong_content_brief_use",
    ):
        lines.append(f"| {key} | {_fmt(m.get(key))} | {_fmt(delta.get(key))} |")
    f = m["facts"]
    lines.append(f"| facts correct/omitted/wrong | {f['correct']}/{f['omitted']}/{f['wrong']} | |")
    c = m.get("coaching") or {}
    if c:
        lines.append(
            f"| coaching raised/missed/contradicted | {c['raised']}/{c['missed']}/{c['contradicted']} "
            f"| {_fmt(delta.get('coaching_raised_rate'))} |"
        )
    lines += ["", "## Per guide (facts)", "", "| Guide | Correct | Omitted | Wrong | Missing |", "|---|---|---|---|---|"]
    per: dict[str, dict[str, int]] = {}
    for row in report["facts"]:
        t = per.setdefault(row["guide"], {"correct": 0, "omitted": 0, "wrong": 0, "missing": 0})
        t[row["verdict"]] += 1
        t["missing"] = int(row["guide_missing"])
    for guide, t in sorted(per.items()):
        lines.append(f"| {guide} | {t['correct']} | {t['omitted']} | {t['wrong']} | {'yes' if t['missing'] else ''} |")
    lines += ["", "## Adversarial cases", ""]
    for case in report["adversarial"]:
        lines.append(f"- {'✅' if case['passed'] else '❌'} {case['case']} — {case['detail']}")
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _write(report: dict[str, Any], baseline: bool) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = "baseline" if baseline else datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS / f"{stem}.json"
    path.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False) + "\n")
    (REPORTS / f"{stem}.md").write_text(_markdown(report))
    return path


# --- datasheet --------------------------------------------------------------------------


async def datasheet(args: argparse.Namespace) -> int:
    from backend.app.services.guide_pipeline.briefing import build_briefing
    from backend.app.services.guide_pipeline.datasheet import build_data_sheet, format_data_sheet_table
    from wcl_agent.game.roster import load_roster

    cls, _, spec = args.spec.partition("/")
    await load_roster()
    briefing = await build_briefing(cls, spec, args.content_type)
    sheet = await build_data_sheet(briefing)
    print(format_data_sheet_table(sheet))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    if args.cmd == "datasheet":
        return asyncio.run(datasheet(args))
    try:
        report = asyncio.run(run(args))
    except Exception:  # noqa: BLE001 - exit code 2 = run error
        logger.exception("accuracy check failed to run")
        return EXIT_ERROR
    path = _write(report, args.baseline)
    print(f"report: {path}")
    print(f"gate: {'PASSED' if report['gate']['passed'] else 'FAILED'}")
    for reason in report["gate"]["reasons"]:
        print(f"  - {reason}")
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
