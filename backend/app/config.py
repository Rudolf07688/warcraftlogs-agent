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
    database_url: str = "postgresql+asyncpg://wcl:wcl@localhost:5432/wcl"

    # Warcraft Logs (also consumed by wcl_agent.wcl_client via os.getenv)
    wcl_client_id: str = ""
    wcl_client_secret: str = ""

    # Model allow-list + default (comma-separated env: WCL_MODELS / WCL_DEFAULT_MODEL)
    wcl_models: str = "gemini-2.5-flash"
    wcl_default_model: str = "gemini-2.5-flash"

    # CORS origins for the local frontend (comma-separated)
    cors_origins: str = "http://localhost:5173"

    @property
    def model_list(self) -> list[str]:
        return [m.strip() for m in self.wcl_models.split(",") if m.strip()]

    @property
    def default_model(self) -> str:
        return self.wcl_default_model or (self.model_list[0] if self.model_list else "gemini-2.5-flash")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
