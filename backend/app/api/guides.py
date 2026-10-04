"""REST: the shared, GLOBAL spec-guide library (feature 008 / US2).

Guides are generic class/spec content shared across all tenants, so these endpoints use the
**non-tenant** DB dependency (``db/session.get_session``) rather than the tenant-scoped one —
but they still require authentication, and mutations require CSRF and are rate-limited
(the table holds no user data; plan Complexity Tracking).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.constants import CLASS_SPECS

from ..auth.dependencies import require_csrf, require_session
from ..auth.rate_limit import guide_limiter
from ..db import repository as repo
from ..db.session import get_session
from ..schemas import GuideGenerateIn, GuideListItem, GuideListOut, GuideOut
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


@router.get("", response_model=GuideListOut)
async def list_guides(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideListOut:
    """Full class/spec roster (from CLASS_SPECS) merged with library status (SC-002)."""
    rows = await repo.list_spec_guides(db)
    return GuideListOut(guides=[GuideListItem(**item) for item in build_guide_roster(rows)])


@router.get("/{class_name}/{spec}", response_model=GuideOut)
async def get_guide(
    class_name: str,
    spec: str,
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> GuideOut:
    _validate_spec(class_name, spec)
    guide = await repo.get_spec_guide(db, class_name=class_name, spec=spec)
    if guide is None:
        return GuideOut(class_name=class_name, spec=spec, status="none")
    return GuideOut(
        class_name=class_name,
        spec=spec,
        status=guide.status,
        guide_markdown=guide.guide_markdown if guide.status == "ready" else None,
        updated_at=guide.updated_at,
    )


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
    return GuideOut(
        class_name=class_name,
        spec=spec,
        status=guide.status,
        guide_markdown=guide.guide_markdown if guide.status == "ready" else None,
        updated_at=guide.updated_at,
    )
