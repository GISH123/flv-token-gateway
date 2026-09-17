import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from app.settings import Settings


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        gateway_host="0.0.0.0",
        gateway_http_port=18080,
        gateway_https_port=18088,
        gateway_enable_http=True,
        gateway_enable_https=True,
        gateway_log_level="info",
        public_base_url="https://10.2.192.9:18088",
        upstream_base_url="http://upstream.test",
        token_secret="0123456789abcdef0123456789abcdef",
        token_ttl_seconds=600,
        token_issuer_api_key="",
        upstream_verify_tls=True,
        cors_allow_origins="*",
        test_stream_path="/gishtest/gish.flv",
        tls_cert_file="certs/gateway.crt",
        tls_key_file="certs/gateway.key",
    )


@pytest.mark.asyncio
async def test_http_health_is_served_without_redirect():
    app = create_app(make_settings())

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://10.2.192.9:18080",
        follow_redirects=False,
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "location" not in response.headers


@pytest.mark.asyncio
async def test_http_get_token_is_served_without_redirect():
    app = create_app(make_settings())

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://10.2.192.9:18080",
        follow_redirects=False,
    ) as client:
        response = await client.get(
            "/api/v1/tokens",
            params={"stream_path": "/gishtest/gish.flv"},
        )

    assert response.status_code == 200
    assert "location" not in response.headers
    assert response.json()["stream_url"].startswith(
        "http://10.2.192.9:18080/gishtest/gish.flv?token="
    )
