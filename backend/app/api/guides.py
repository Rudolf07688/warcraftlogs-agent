"""REST: the shared, GLOBAL spec-guide library (features 008, 009, 015).

Feature 015: every guide is one content type (``raid`` | ``mplus``) of one spec; the list
returns one row per spec with both summaries, and the viewer/generate routes take the
content type as the last path segment (anything else → 422).

Guides are generic class/spec content shared across all tenants, so these endpoints use the
**non-tenant** DB dependency (``db/session.get_session``) rather than the tenant-scoped one —
but they still require authentication, and mutations require CSRF and are rate-limited
(the table holds no user data; plan Complexity Tracking).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.game.roster import roster_snapshot
from wcl_agent.game.patch import current_mplus_season, current_patch
from wcl_agent.client.wcl_client import background_lane

from ..auth.dependencies import require_csrf, require_session
from ..auth.rate_limit import guide_limiter, guide_report_limiter
from ..db import repository as repo
from ..db.models import SpecGuide
from ..db.session import get_session
from ..schemas import (
    ContentType,
    GuideGenerateIn,
    GuideListItem,
    GuideListOut,
    GuideOut,
    GuideReportIn,
    GuideReportOut,
    GuideSource,
)
from ..services.guide import (
    build_guide_roster,
    ensure_guide,
    maybe_scan_stale_guides,
    stale_and_idle,
    summarize_guide,
    touch_guide_wanted,
)
from ..services.guide_pipeline.render import strip_claim_markers
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/guides", tags=["guides"])

# Fixed-window length (seconds) used for the Retry-After hint on a rate-limited generate.
_RATE_WINDOW_S = 60


def _validate_spec(class_name: str, spec: str) -> None:
    """404 unless ``(class_name, spec)`` is a known member of the roster (SSOT)."""
    if not roster_snapshot().has(class_name, spec):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Unknown class/spec."},
        )


async def _live_context() -> tuple[str | None, str | None]:
    """The live patch and Mythic+ season (cached WCL zone list), in the background lane."""
    with background_lane():
        return await current_patch(), await current_mplus_season()


def _sources(raw: list | None) -> list[GuideSource]:
    out = []
    for s in raw or []:
        if isinstance(s, dict) and s.get("uri"):
            try:
                out.append(GuideSource.model_validate(s))
            except ValueError:
                out.append(GuideSource(title=s.get("title"), uri=s["uri"]))
    return out


def _issue_texts(issues: list | None) -> list[str]:
    texts = []
    for issue in issues or []:
        if isinstance(issue, dict):
            text = issue.get("detail") or issue.get("check") or ""
            item = issue.get("item")
            texts.append(f"{item}: {text}" if item and text else text or str(item or ""))
        elif issue:
            texts.append(str(issue))
    return [t for t in texts if t]


async def _guide_out(
    class_name: str, spec: str, content_type: str, guide: SpecGuide | None
) -> GuideOut:
    """The viewer shape for one content type (contracts/guides-api.md ``display`` rules)."""
    live_patch, live_season = await _live_context() if guide is not None else (None, None)
    summary = summarize_guide(guide, content_type, live_patch, live_season)
    out = GuideOut(class_name=class_name, spec=spec, **summary)
    if guide is None:
        return out
    if out.has_published:
        out.display = "published"
        out.guide_markdown = strip_claim_markers(guide.guide_markdown)
        out.sources = _sources(guide.sources)
        out.unconfirmed = list((guide.brief or {}).get("unconfirmed") or [])
    elif guide.status == "needs_review" and guide.draft:
        draft = guide.draft
        out.display = "draft"
        out.guide_markdown = strip_claim_markers(draft.get("markdown"))
        out.unconfirmed = list((draft.get("brief") or {}).get("unconfirmed") or [])
        out.review_issues = _issue_texts(guide.review_issues)
    if guide.status == "failed":
        out.failure_reason = guide.failure_reason
    return out


@router.get("", response_model=GuideListOut)
async def list_guides(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideListOut:
    """Full live class/spec roster × both content types, merged with library status (SC-002)."""
    maybe_scan_stale_guides()  # throttled, non-blocking (FR-050)
    rows = await repo.list_spec_guides(db, with_text=False)  # status only (PERF-014)
    live_patch, live_season = await _live_context() if rows else (None, None)
    return GuideListOut(
        guides=[GuideListItem(**item) for item in build_guide_roster(rows, live_patch, live_season)],
        roster_source=roster_snapshot().source,
    )


@router.get("/{class_name}/{spec}/{content_type}", response_model=GuideOut)
async def get_guide(
    class_name: str,
    spec: str,
    content_type: ContentType,
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideOut:
    _validate_spec(class_name, spec)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec, content_type=content_type)
    if guide is not None:
        touch_guide_wanted([(class_name, spec, content_type)])  # opened ⇒ in use (FR-051)
        if stale_and_idle(guide):
            await ensure_guide(class_name, spec, content_type)  # regenerate "on next open"
            guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec, content_type=content_type)
    return await _guide_out(class_name, spec, content_type, guide)


@router.post("/{class_name}/{spec}/{content_type}/generate", response_model=GuideOut)
async def generate_guide(
    class_name: str,
    spec: str,
    content_type: ContentType,
    body: GuideGenerateIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_session),
) -> GuideOut:
    """Request/retry/refresh one content type's guide (best-effort, non-blocking).

    Rate-limited per user; never starts the other content type (FR-027).
    """
    _validate_spec(class_name, spec)
    if not guide_limiter.allow_request(str(identity.user_id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many guide requests. Slow down."},
            headers={"Retry-After": str(_RATE_WINDOW_S)},
        )
    # Idempotent: pending, or ready & fresh & !force ⇒ no-op; otherwise spawn generation.
    await ensure_guide(class_name, spec, content_type, force=body.force)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec, content_type=content_type)
    if guide is None:
        # ensure_guide upserts pending before spawning; a None here means a concurrent
        # race left no row yet — report pending (generation is in flight).
        return GuideOut(class_name=class_name, spec=spec, content_type=content_type, status="pending")
    return await _guide_out(class_name, spec, content_type, guide)


@router.post(
    "/{class_name}/{spec}/{content_type}/reports", response_model=GuideReportOut, status_code=201
)
async def report_guide(
    class_name: str,
    spec: str,
    content_type: ContentType,
    body: GuideReportIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_session),
) -> GuideReportOut:
    """"Report an inaccuracy" on a published guide (FR-052). The next regeneration's
    reviewer judges it against the evidence and marks it fixed or rejected."""
    _validate_spec(class_name, spec)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec, content_type=content_type)
    if guide is None or not repo.guide_has_published(guide):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "There is no published guide to report."},
        )
    if not guide_report_limiter.allow_request(str(identity.user_id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many reports. Slow down."},
            headers={"Retry-After": str(_RATE_WINDOW_S)},
        )
    report = await repo.create_guide_report(
        db,
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        user_id=identity.user_id,
        note=body.note,
        guide_generated_at=guide.generated_at,
    )
    await db.commit()
    return GuideReportOut.model_validate(report)
