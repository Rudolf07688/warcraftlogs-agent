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
    # Connection pool (PERF-006). Shared by the app and ADK's session store. A chat turn
    # now holds a connection only for short transactions, never across the model stream.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: float = 10.0

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
    wcl_guide_model: str = "gemini-3.7-flash"

    # Per-user cap on manual spec-guide generation requests (feature 008 / US2, FR-014).
    # Bounds user-initiated generation so a burst can't cascade into WCL/model rate limits.
    wcl_guide_generate_per_minute: int = 10
    # PERF-012: at most this many background guide/guild-summary generations run at once,
    # so filling in a profile can't flood the model quota the player's chat depends on.
    wcl_guide_max_concurrency: int = 2

    # feature 015: grounded guide pipeline (contracts/guide-pipeline.md §Config).
    wcl_guide_review_model: str = "gemini-3.1-pro-preview"  # reviewer; must differ from the author
    wcl_guide_max_review_rounds: int = 3  # checks + review rounds before a run is held (FR-047)
    wcl_guide_brief_max_chars: int = 6000  # one coaching brief, never truncated (FR-010)
    wcl_guide_preamble_briefs_max_chars: int = 12000  # whole briefs inlined per chat turn (FR-013)
    wcl_guide_datasheet_min_sample: int = 20  # ranked players a data sheet needs to be citable
    wcl_guide_inuse_days: int = 14  # stale guides wanted this recently regenerate at once (FR-051)
    wcl_guide_report_per_minute: int = 5  # per-user cap on "report an inaccuracy"
    wcl_guide_research_fetch_enabled: bool = False  # fetch allowlisted third-party pages (terms review first)
    wcl_guide_talent_names_url: str = ""  # optional talent id → name JSON; off until terms are checked
    wow_version_url: str = "https://us.version.battle.net/v2/products/wow/versions"  # live build
    wow_news_url: str = "https://worldofwarcraft.blizzard.com/en-us/news"  # hotfix article discovery

    # Findings-report synthesis (feature 007 / US2-US3). A plain (non-web-search) model
    # that summarizes in-scope chat content into an analytic findings document. Runs
    # off the event loop with a bounded timeout; independent of the user's chat model.
    wcl_report_model: str = "gemini-3.6-flash"

    # Feature 011: model rate-limit relief. Rate-limited / overloaded model refusals are
    # retried with exponential backoff (initial → max, base 2, jitter) until the attempt
    # count or the total wait budget per model request is spent; other errors fail fast.
    # The round cap is the number of lookup rounds a turn may use before the agent is
    # told to wrap up with the evidence it has. Runners are cached per model, so a change
    # needs a backend restart. See wcl_agent/model_retry.py.
    wcl_model_retry_attempts: int = 5
    wcl_model_retry_initial_s: float = 2.0
    wcl_model_retry_max_s: float = 30.0
    wcl_model_retry_budget_s: float = 90.0
    wcl_turn_round_cap: int = 6

    # feature 014: shared Redis cache for WCL data (also read by wcl_agent.cache via
    # os.getenv; documented here). No REDIS_URL, or WCL_CACHE_ENABLED=false, means no
    # cache: every lookup goes straight to WCL. TTLs are per key family, in seconds; the
    # OAuth token always follows its own expiry. See contracts/config-and-compose.md.
    redis_url: str = ""
    wcl_cache_enabled: bool = True
    wcl_cache_ttl_char_id: int = 86400
    wcl_cache_ttl_char_overview: int = 600
    wcl_cache_ttl_char_reports: int = 300
    wcl_cache_ttl_report_summary: int = 86400
    wcl_cache_ttl_report_player: int = 86400
    wcl_cache_ttl_world_zones: int = 3600
    wcl_cache_unfinished_ttl: int = 120  # reports still being logged
    wcl_cache_jitter: float = 0.10  # TTL × U(1, 1 + jitter)
    wcl_cache_lock_ms: int = 90000  # loader lock lifetime; longer than the 75 s query timeout
    wcl_cache_lock_wait_ms: int = 2000  # how long a lock loser polls for the winner's value
    wcl_neg_cache_ttl: int = 60  # "character not found" marker
    wcl_metrics_retention_days: int = 35

    # feature 013: WCL lanes and timeouts (also read by wcl_agent.wcl_client via os.getenv).
    # Background work (guides, patch lookup, recent raids) holds at most this many of the
    # WCL_MAX_CONCURRENCY slots; one query (slot wait + request) is bounded by the timeout.
    wcl_background_concurrency: int = 2
    wcl_query_timeout_s: int = 75

    # feature 013: welcome-page recent raids. A refresh starts at most every
    # `refresh_min_s`; a `running` claim older than `stale_s` is reclaimable (crash/restart).
    recent_raids_refresh_min_s: int = 900
    recent_raids_stale_s: int = 300
    recent_raids_limit: int = 20
    recent_raids_refresh_timeout_s: int = 120

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
