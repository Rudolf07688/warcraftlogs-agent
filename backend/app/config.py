"""Backend settings, read from environment (root .env locally, Secret Manager in prod).

Config is env-var based so the secret *source* can change per environment without
code changes (spec FR-017). Google auth is handled by ADC via the standard
GOOGLE_* env vars / mounted credentials (FR-016) — not read here.
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populate os.environ from a local .env so ADK / wcl_client (which use os.getenv)
# work in local dev. Harmless in containers/Cloud Run where env is already set.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    # `database_url` is the **runtime** role (non-superuser, no BYPASSRLS — RLS applies).
    # `database_owner_url` is the **migration-owner** role used ONLY by Alembic (owns the
    # tables, can ALTER/enable RLS). Defaults to the runtime URL for simple single-role dev
    # setups; production MUST set a distinct owner URL (research R4). (feature 006)
    database_url: str = "postgresql+asyncpg://wcl:wcl@localhost:5432/wcl"
    database_owner_url: str = ""

    # --- Auth / session / tenancy (feature 006) -------------------------------
    # Session cookie. `__Host-` prefix REQUIRES Secure + Path=/ + no Domain, so the
    # browser pins it to this exact host (same-origin via the Vite/reverse proxy).
    session_cookie_name: str = "__Host-session"
    session_cookie_secure: bool = True  # set False only for plain-HTTP local dev
    session_cookie_samesite: str = "lax"
    # Lifetimes (seconds). Idle: re-up on use; absolute: hard cap regardless of activity.
    session_idle_max_age_s: int = 60 * 60 * 24 * 7  # 7 days idle
    session_absolute_max_age_s: int = 60 * 60 * 24 * 30  # 30 days absolute
    session_last_seen_throttle_s: int = 300  # write last_seen_at at most every 5 min
    # Single-use public tokens.
    invitation_ttl_s: int = 60 * 60 * 24  # 24h
    password_reset_ttl_s: int = 60 * 60  # 1h
    token_entropy_bytes: int = 32  # secrets.token_bytes(N) for sessions/csrf/invites/resets
    # Password policy (guide §Password hashing): long minimum, generous max.
    password_min_length: int = 15
    password_max_length: int = 256
    # Argon2id is CPU-bound and offloaded to a thread pool; cap concurrency so hashing
    # cannot exhaust CPU/memory under a login flood (research R2).
    password_hash_max_concurrency: int = 4
    # Progressive login throttle (research R7): never a permanent lockout.
    login_failure_block_threshold: int = 5  # consecutive failures before delay kicks in
    login_block_max_delay_s: int = 30  # capped delay ceiling
    rate_limit_token_per_minute: int = 20  # per-source cap on public token endpoints
    # Canonical site URL used to build invite/reset links (never the inbound Host header)
    # and to validate WS/CSRF Origin. No trailing slash.
    site_url: str = "http://localhost:5173"
    # Server secret for HMAC-deriving per-session CSRF tokens (stateless: recomputable on
    # every /me, so a page reload recovers the token). MUST be set to a strong random
    # value in production; the dev default is intentionally obvious.
    secret_key: str = "dev-insecure-change-me"

    @property
    def owner_database_url(self) -> str:
        """Migration-owner URL (falls back to the runtime URL in simple dev setups)."""
        return self.database_owner_url or self.database_url

    # Warcraft Logs (also consumed by wcl_agent.wcl_client via os.getenv)
    wcl_client_id: str = ""
    wcl_client_secret: str = ""

    # Fallback allow-list + default (comma-separated env: WCL_MODELS / WCL_DEFAULT_MODEL).
    # The live dropdown is the startup-validated set (US4); these are the documented
    # fallback served if discovery/validation can't run.
    wcl_models: str = "gemini-3.6-flash,gemini-3.1-pro-preview"
    wcl_default_model: str = "gemini-3.6-flash"

    # Candidate models to discover + probe at startup (US4). Gemini ids pass through
    # to Vertex; Anthropic-on-Vertex ids run Claude via Model Garden.
    wcl_gemini_models: str = "gemini-3.6-flash,gemini-3.1-pro-preview"
    wcl_anthropic_models: str = ""

    # CORS origins for the local frontend (comma-separated)
    cors_origins: str = "http://localhost:5173"

    # Background spec-guide generation (US6). A web-search-capable model so guides
    # reflect the current retail patch. Runs over a disposable session like the greeting.
    wcl_guide_model: str = "gemini-3.6-flash"

    # WCL query cache TTLs in seconds (US4). Report-scoped data is effectively immutable
    # (~24h); leaderboard/ranking data is volatile (~1h).
    wcl_cache_ttl_report_s: int = 86400
    wcl_cache_ttl_leaderboard_s: int = 3600

    @property
    def model_list(self) -> list[str]:
        return [m.strip() for m in self.wcl_models.split(",") if m.strip()]

    @property
    def gemini_models(self) -> list[str]:
        return [m.strip() for m in self.wcl_gemini_models.split(",") if m.strip()]

    @property
    def anthropic_models(self) -> list[str]:
        return [m.strip() for m in self.wcl_anthropic_models.split(",") if m.strip()]

    @property
    def candidate_models(self) -> list[str]:
        """De-duplicated candidate set for startup discovery (Gemini + Anthropic)."""
        seen: dict[str, None] = {}
        for m in [*self.gemini_models, *self.anthropic_models]:
            seen.setdefault(m, None)
        return list(seen)

    @property
    def default_model(self) -> str:
        return self.wcl_default_model or (self.model_list[0] if self.model_list else "gemini-3.6-flash")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
