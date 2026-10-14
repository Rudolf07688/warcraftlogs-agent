"""REST: the shared, GLOBAL spec-guide library (feature 008 / US2; feature 009 / US5 freshness).

Guides are generic class/spec content shared across all tenants, so these endpoints use the
**non-tenant** DB dependency (``db/session.get_session``) rather than the tenant-scoped one —
but they still require authentication, and mutations require CSRF and are rate-limited
(the table holds no user data; plan Complexity Tracking).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.constants import CLASS_SPECS
from wcl_agent.patch import current_patch, guide_freshness

from ..auth.dependencies import require_csrf, require_session
from ..auth.rate_limit import guide_limiter
from ..db import repository as repo
from ..db.models import SpecGuide
from ..db.session import get_session
from ..schemas import GuideGenerateIn, GuideListItem, GuideListOut, GuideOut, GuideSource
from ..services.guide import build_guide_roster, ensure_spec_guide
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/guides", tags=["guides"])

# Fixed-window length (seconds) used for the Retry-After hint on a rate-limited generate.
_RATE_WINDOW_S = 60


def _validate_spec(class_name: str, spec: str) -> None:
    """404 unless ``(class_name, spec)`` is a known member of the roster (SSOT)."""
    info = CLASS_SPECS.get(class_name)
    if info is None or spec not in info["specs"]:  # type: ignore[operator]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Unknown class/spec."},
        )


async def _live_patch() -> str | None:
    """The current raid patch (blocking WCL lookup, cached by the client) off the loop."""
    return await asyncio.to_thread(current_patch)


async def _guide_out(class_name: str, spec: str, guide: SpecGuide | None) -> GuideOut:
    """One response shape for detail + generate (feature 009 adds freshness/sources)."""
    if guide is None:
        return GuideOut(class_name=class_name, spec=spec, status="none")
    ready = guide.status == "ready"
    freshness = guide_freshness(guide.game_patch, await _live_patch()) if ready else None
    sources = [
        GuideSource(title=s.get("title"), uri=s["uri"])
        for s in (guide.sources or [])
        if isinstance(s, dict) and s.get("uri")
    ]
    return GuideOut(
        class_name=class_name,
        spec=spec,
        status=guide.status,
        guide_markdown=guide.guide_markdown if ready else None,
        updated_at=guide.updated_at,
        game_patch=guide.game_patch,
        generated_at=guide.generated_at,
        freshness=freshness,
        sources=sources,
    )


@router.get("", response_model=GuideListOut)
async def list_guides(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideListOut:
    """Full class/spec roster (from CLASS_SPECS) merged with library status (SC-002)."""
    rows = await repo.list_spec_guides(db, with_text=False)  # status only (PERF-014)
    live = await _live_patch() if any(r.status == "ready" for r in rows) else None
    return GuideListOut(guides=[GuideListItem(**item) for item in build_guide_roster(rows, live)])


@router.get("/{class_name}/{spec}", response_model=GuideOut)
async def get_guide(
    class_name: str,
    spec: str,
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideOut:
    _validate_spec(class_name, spec)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec)
    return await _guide_out(class_name, spec, guide)


@router.post("/{class_name}/{spec}/generate", response_model=GuideOut)
async def generate_guide(
    class_name: str,
    spec: str,
    body: GuideGenerateIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_session),
) -> GuideOut:
    """Request/retry/refresh a guide (best-effort, non-blocking). Rate-limited per user."""
    _validate_spec(class_name, spec)
    if not guide_limiter.allow_request(str(identity.user_id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many guide requests. Slow down."},
            headers={"Retry-After": str(_RATE_WINDOW_S)},
        )
    # Idempotent: ready&!force or pending ⇒ no-op; absent|failed|force ⇒ spawn generation.
    await ensure_spec_guide(class_name, spec, force=body.force)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec)
    if guide is None:
        # ensure_spec_guide upserts pending before spawning; a None here means a concurrent
        # race left no row yet — report pending (generation is in flight).
        return GuideOut(class_name=class_name, spec=spec, status="pending")
    return await _guide_out(class_name, spec, guide)
