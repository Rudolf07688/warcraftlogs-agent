"""Backend settings, read from environment (root .env locally, Secret Manager in prod).

Config is env-var based so the secret *source* can change per environment without
code changes (spec FR-017). Google auth is handled by ADC via the standard
GOOGLE_* env vars / mounted credentials (FR-016) — not read here.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wcl_agent.llm import provider
from wcl_agent.llm.models import ClassSetting, parse_class_settings
from wcl_agent.llm.provider import ModelRole, role_model

# Populate os.environ from a local .env so ADK / wcl_client (which use os.getenv)
# work in local dev. Harmless in containers/Cloud Run where env is already set.
load_dotenv()

logger = logging.getLogger(__name__)


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
    # Reverse proxies whose X-Forwarded-For is believed when keying those limits (sc-158):
    # comma-separated IPs or CIDRs, e.g. "10.0.0.0/8,127.0.0.1". Empty trusts nothing, so
    # the direct peer is the client.
    trusted_proxies: str = ""
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

    # Warcraft Logs (also consumed by wcl_agent.client.wcl_client via os.getenv)
    wcl_client_id: str = ""
    wcl_client_secret: str = ""

    # Fallback allow-list + default (comma-separated env: WCL_MODELS / WCL_DEFAULT_MODEL).
    # The live dropdown is the startup-validated set (US4); these are the documented
    # fallback served if discovery/validation can't run. Feature 032: the model roles
    # (default chat, report, guide, guide review, suggest, greeting) are empty here and
    # resolved per provider in ``_resolve_roles`` (WCL_LLM_PROVIDER, wcl_agent.llm.provider);
    # an explicit value wins when the active provider serves it.
    wcl_models: str = "gemini-3.6-flash,gemini-3.1-pro-preview"
    wcl_default_model: str = ""
    # Follow-up suggestions and chat titles (the fast role), and the new-chat greeting.
    wcl_suggest_model: str = ""
    wcl_greeting_model: str = ""

    # Candidate models to discover + probe at startup (US4). Gemini ids pass through
    # to Vertex; Claude ids run on the active provider (Vertex's Model Garden or the
    # Anthropic API), each read in that provider's id form.
    wcl_gemini_models: str = "gemini-3.6-flash,gemini-3.1-pro-preview"
    wcl_anthropic_models: str = ""

    # Feature 016: `catalog` builds the dropdown from Vertex's Model Garden catalog (the
    # newest working versions per class, `name:count` in serving order); `static` probes
    # only the lists above, which are also the fallback when the catalog can't be listed.
    # Where models run is WCL_MODEL_LOCATION (read by wcl_agent.llm.vertex, default global).
    wcl_model_discovery: str = "catalog"
    wcl_gemini_classes: str = "pro:2,flash:2,flash-lite:2"
    wcl_anthropic_classes: str = "haiku:1,sonnet:1,opus:1"

    # CORS origins for the local frontend (comma-separated)
    cors_origins: str = "http://localhost:5173"

    # Background spec-guide generation (US6). A web-search-capable model so guides
    # reflect the current retail patch. Runs over a disposable session like the greeting.
    # A model role (feature 032): resolved per provider.
    wcl_guide_model: str = ""

    # Per-user cap on manual spec-guide generation requests (feature 008 / US2, FR-014).
    # Bounds user-initiated generation so a burst can't cascade into WCL/model rate limits.
    wcl_guide_generate_per_minute: int = 10
    # PERF-012: at most this many background guide/guild-summary generations run at once,
    # so filling in a profile can't flood the model quota the player's chat depends on.
    wcl_guide_max_concurrency: int = 2

    # feature 015: grounded guide pipeline (contracts/guide-pipeline.md §Config).
    wcl_guide_review_model: str = ""  # reviewer role; must differ from the author
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
    # A model role (feature 032): resolved per provider.
    wcl_report_model: str = ""

    # Feature 011: model rate-limit relief. Rate-limited / overloaded model refusals are
    # retried with exponential backoff (initial → max, base 2, jitter) until the attempt
    # count or the total wait budget per model request is spent; other errors fail fast.
    # The round cap is the number of lookup rounds a turn may use before the agent is
    # told to wrap up with the evidence it has. Runners are cached per model, so a change
    # needs a backend restart. See wcl_agent/llm/model_retry.py.
    wcl_model_retry_attempts: int = 5
    wcl_model_retry_initial_s: float = 2.0
    wcl_model_retry_max_s: float = 30.0
    wcl_model_retry_budget_s: float = 90.0
    wcl_turn_round_cap: int = 6

    # feature 014: shared Redis cache for WCL data (also read by wcl_agent.cache.cache via
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
    wcl_cache_ttl_report_participants: int = 86400
    wcl_cache_ttl_world_zones: int = 3600
    wcl_cache_unfinished_ttl: int = 120  # reports still being logged
    wcl_cache_jitter: float = 0.10  # TTL × U(1, 1 + jitter)
    wcl_cache_lock_ms: int = 90000  # loader lock lifetime; longer than the 75 s query timeout
    wcl_cache_lock_wait_ms: int = 2000  # how long a lock loser polls for the winner's value
    wcl_neg_cache_ttl: int = 60  # "character not found" marker
    wcl_metrics_retention_days: int = 35

    # feature 013: WCL lanes and timeouts (also read by wcl_agent.client.wcl_client via os.getenv).
    # Background work (guides, patch lookup, recent raids) holds at most this many of the
    # WCL_MAX_CONCURRENCY slots; one query (slot wait + request) is bounded by the timeout.
    wcl_background_concurrency: int = 2
    wcl_query_timeout_s: int = 75

    # feature 020: every successful WCL response is upserted into `raw_fetches` by a
    # background writer. At most this many responses / MB of response bytes wait to be
    # written; beyond that new ones are dropped (and counted in the log), never blocked.
    wcl_fetch_persist_enabled: bool = True
    wcl_fetch_persist_queue_max: int = 500
    wcl_fetch_persist_queue_mb: int = 64
    # feature 039: DB-first reads. A WCL query is answered from `raw_fetches` when the row is
    # visible to the tenant (public report, or a code the tenant fetched itself) and fresh.
    # "Public" and a tenant's grant count for this many days, then WCL is asked again. With
    # Redis back-filled from the store, a report made private stays reachable by code for at
    # most this plus the Redis TTL (24 h), so keep it short (039 research R9).
    wcl_store_reads_enabled: bool = True
    raw_store_reverify_days: int = 1
    # feature 045 (PERF-001): a store read costs at most this, then the query goes to WCL; a
    # timeout or connection error also keeps the store out of the way for 30 s.
    raw_store_probe_timeout_ms: int = 400
    # feature 043: the knowledge base. Stored WCL fetches, published guides and finished chat
    # exchanges become chunks in a background queue (bounded; a full queue drops the job, and
    # the backfill only picks up sources with no chunks yet: a dropped update stays stale),
    # embedded with `kb_embed_model` at 768 dimensions. Without embeddings chunks stay
    # keyword-searchable; rows still missing a vector are retried every
    # `kb_embed_sweep_s`. `kb_embed_request_batch` texts go in one Vertex request; the price
    # (USD per 1M input tokens) only feeds the backfill's cost estimate.
    kb_index_enabled: bool = True
    kb_embed_enabled: bool = True
    kb_embed_model: str = "gemini-embedding-001"
    kb_index_queue_max: int = 1000
    kb_embed_batch: int = 32
    kb_embed_request_batch: int = 1
    kb_embed_sweep_s: int = 600
    kb_embed_price_per_mtok: float = 0.15

    # feature 013: welcome-page recent raids. A refresh starts at most every
    # `refresh_min_s`; a `running` claim older than `stale_s` is reclaimable (crash/restart).
    recent_raids_refresh_min_s: int = 900
    recent_raids_stale_s: int = 300
    recent_raids_limit: int = 20
    # Welcome page display caps (feature 022); the limit above is the WCL listing depth.
    recent_raids_shown: int = 6
    recent_mplus_shown: int = 6
    recent_raids_refresh_timeout_s: int = 120

    @field_validator("trusted_proxies")
    @classmethod
    def _check_trusted_proxies(cls, value: str) -> str:
        _parse_networks(value)  # a typo fails at startup, not at the first login
        return value

    @model_validator(mode="after")
    def _resolve_roles(self) -> Settings:
        """Each model role: its explicit value if the active provider serves it, else the
        provider's default (feature 032), so switching providers takes one ``.env`` line."""
        self.wcl_default_model = role_model(ModelRole.CHAT, self.wcl_default_model)
        self.wcl_report_model = role_model(ModelRole.REPORT, self.wcl_report_model)
        self.wcl_guide_model = role_model(ModelRole.GUIDE, self.wcl_guide_model)
        self.wcl_guide_review_model = role_model(ModelRole.GUIDE_REVIEW, self.wcl_guide_review_model)
        self.wcl_suggest_model = role_model(ModelRole.FAST, self.wcl_suggest_model)
        self.wcl_greeting_model = role_model(ModelRole.GREETING, self.wcl_greeting_model)
        return self

    @property
    def llm_provider(self) -> provider.Provider:
        return provider.active_provider()

    # Feature 032: the model lists keep only the ids the active provider serves, in its id
    # form; under `anthropic` an empty list falls back to the Claude role defaults.
    @property
    def model_list(self) -> list[str]:
        return provider.served_ids(self.wcl_models.split(",")) or provider.default_candidates()

    @property
    def gemini_models(self) -> list[str]:
        return provider.served_ids(self.wcl_gemini_models.split(","))

    @property
    def anthropic_models(self) -> list[str]:
        return provider.served_ids(self.wcl_anthropic_models.split(",")) or provider.default_candidates()

    @property
    def candidate_models(self) -> list[str]:
        """De-duplicated candidate set for startup discovery (Gemini + Anthropic)."""
        seen: dict[str, None] = {}
        for m in [*self.gemini_models, *self.anthropic_models]:
            seen.setdefault(m, None)
        return list(seen)

    @property
    def model_discovery_mode(self) -> Literal["catalog", "static"]:
        mode = self.wcl_model_discovery.strip().lower()
        if mode not in ("catalog", "static"):
            logger.warning("WCL_MODEL_DISCOVERY=%r is not catalog or static; using catalog", mode)
            mode = "catalog"
        if mode == "catalog" and not provider.has_model_catalog():
            logger.info("no model catalog for %s; probing the static lists", self.llm_provider)
            return "static"
        return mode  # type: ignore[return-value]

    @property
    def gemini_classes(self) -> list[ClassSetting]:
        if self.llm_provider == "anthropic":
            return []  # the Anthropic API serves no Gemini
        return parse_class_settings("google", self.wcl_gemini_classes)

    @property
    def anthropic_classes(self) -> list[ClassSetting]:
        return parse_class_settings("anthropic", self.wcl_anthropic_classes)

    @property
    def default_model(self) -> str:
        return self.wcl_default_model or (self.model_list[0] if self.model_list else "gemini-3.6-flash")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return _parse_networks(self.trusted_proxies)


def _parse_networks(value: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(p.strip(), strict=False) for p in value.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
