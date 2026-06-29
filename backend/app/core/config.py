from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InvestScope API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://investscope:investscope@db:5432/investscope"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INVESTSCOPE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

