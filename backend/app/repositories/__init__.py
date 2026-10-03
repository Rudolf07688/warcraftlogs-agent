"""Data-access repositories for the auth/tenant tables (feature 006).

These are thin, typed query helpers over the auth/tenant ORM models — the single place
SQL for identity data lives (DRY). Higher-level policy (token generation, cookie
attributes, expiry, audit orchestration) lives in ``app/auth`` and ``app/services``.
"""
