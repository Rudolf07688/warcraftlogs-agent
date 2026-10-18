"""Admin view of "report an inaccuracy" notes on the guide library (feature 015, FR-052).

Read-only; platform admins only. Reports are global like the guides themselves; the list
carries the reporter's user id, never an email.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_platform_admin
from ..db import repository as repo
from ..db.session import get_session
from ..schemas import GuideReportAdminOut
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/guide-reports", response_model=list[GuideReportAdminOut])
async def guide_reports(
    status: Literal["open", "fixed", "rejected"] | None = Query(None),
    _identity: RequestIdentity = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_session),
) -> list[GuideReportAdminOut]:
    return [GuideReportAdminOut.model_validate(r) for r in await repo.list_guide_reports(db, status=status)]
