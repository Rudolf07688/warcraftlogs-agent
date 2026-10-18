"""Admin view of the shared WCL cache: per-family hit rates and Redis health (feature 014, US3).

Read-only; platform admins only. See specs/014-redis-wcl-cache/contracts/cache-stats-api.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from wcl_agent.cache import read_stats

from ..auth.dependencies import require_platform_admin
from ..schemas import CacheStats
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/cache-stats", response_model=CacheStats)
async def cache_stats(
    days: int = Query(7, ge=1, le=35),
    _identity: RequestIdentity = Depends(require_platform_admin),
) -> CacheStats:
    return CacheStats.model_validate(await read_stats(days))
