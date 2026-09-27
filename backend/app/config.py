"""Runtime settings, read from environment variables or backend/.env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "sample" = built-in sample data only (no keys needed, good for demos).
    # "live"   = use every connector that has credentials, fall back to sample for the rest.
    data_mode: str = "sample"

    # Database. SQLite works out of the box; use Postgres in production, e.g.
    # postgresql+psycopg://user:pass@host:5432/sprev
    database_url: str = "sqlite:///./sprev.db"

    # CORS origins for the Next.js app (comma separated).
    cors_origins: str = "http://localhost:3000"

    # --- Connectors -------------------------------------------------------
    # US Census (ACS 5-year). The API works without a key at low volume;
    # a free key raises the limit: https://api.census.gov/data/key_signup.html
    census_api_key: str | None = None
    census_acs_year: int = 2023

    # RentCast: property records, AVM value + comps, long-term rent estimate.
    rentcast_api_key: str | None = None

    # RESO Web API (MLS, or Zillow Group's Bridge API). Requires an MLS / vendor
    # data license. base_url example: https://api.bridgedataoutput.com/api/v2/OData/<dataset>
    reso_base_url: str | None = None
    reso_access_token: str | None = None

    # --- AI layer ----------------------------------------------------------
    # Optional. When set, the written explanation and the letter polish use Claude.
    # All numbers are still computed in Python; the model only writes prose.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # --- Buyer defaults ----------------------------------------------------
    buyer_entity: str = "SP Real Estate Ventures, LLC"


@lru_cache
def get_settings() -> Settings:
    return Settings()
