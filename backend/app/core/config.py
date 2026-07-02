from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InvestScope API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://investscope:investscope@db:5432/investscope"
    cors_origins: list[str] = ["http://localhost:3000"]
    market_data_provider: str = "demo"
    alpha_vantage_api_key: SecretStr | None = None
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    market_data_timeout_seconds: float = 10.0
    alpha_vantage_daily_limit: int = 25
    alpha_vantage_daily_reserve: int = 1
    alpha_vantage_min_interval_seconds: float = 1.5
    alpha_vantage_rate_limit_cooldown_seconds: int = 60
    market_sync_max_days: int = 366
    market_data_stale_after_hours: int = 36
    market_daily_session_close_hour_utc: int = 21
    sec_user_agent: str = "InvestScope contact@example.com"
    sec_max_requests_per_second: float = 1.0
    sec_cache_ttl_hours: int = 24
    sec_ticker_cache_ttl_hours: int = 168
    sec_request_timeout_seconds: float = 30.0
    sec_import_max_file_mb: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INVESTSCOPE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
