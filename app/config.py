from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "GoComet Ride-Hailing Platform"
    env: str = "development"
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database
    database_url: str = "postgresql+asyncpg://rhp:rhp_secret@localhost:5432/ride_hailing"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # New Relic
    new_relic_license_key: str = ""
    new_relic_app_name: str = "GoComet-Ride-Hailing"

    # PSP
    psp_base_url: str = "https://api.stripe.com/v1"
    psp_api_key: str = ""
    psp_timeout_seconds: int = 10

    # Matching
    matching_radius_km: float = 5.0
    matching_timeout_seconds: int = 8
    matching_max_retries: int = 3

    # Surge
    max_surge_multiplier: float = 5.0
    surge_update_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
