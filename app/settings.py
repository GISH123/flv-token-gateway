from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    public_base_url: str = "http://127.0.0.1:8088"
    upstream_base_url: str = "http://127.0.0.1:9090"
    token_secret: str = Field(default="dev-only-secret-change-me-please", min_length=16)
    token_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    token_issuer_api_key: str = ""
    upstream_verify_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
