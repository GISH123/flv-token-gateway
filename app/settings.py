from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gateway_host: str = Field(default="0.0.0.0", min_length=1)
    gateway_port: int = Field(default=18088, ge=1, le=65535)
    gateway_log_level: str = "info"

    public_base_url: str = "http://127.0.0.1:18088"
    upstream_base_url: str = "http://127.0.0.1:9090"

    token_secret: str = Field(default="dev-only-secret-change-me-please", min_length=32)
    token_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    token_issuer_api_key: str = ""
    upstream_verify_tls: bool = True

    cors_allow_origins: str = "*"
    test_stream_path: str = "/gishtest/gish.flv"

    @property
    def cors_origins(self) -> list[str]:
        values = [value.strip() for value in self.cors_allow_origins.split(",") if value.strip()]
        if not values or "*" in values:
            return ["*"]
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
