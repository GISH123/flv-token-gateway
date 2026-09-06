import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from app.settings import Settings


def make_settings():
    return Settings(
        gateway_host="0.0.0.0",
        gateway_http_port=18080,
        gateway_https_port=18088,
        gateway_log_level="info",
        public_base_url="https://gateway.test:18088",
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
async def test_local_flv_js_asset_is_served():
    app = create_app(make_settings())

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://gateway.test:18088",
    ) as client:
        response = await client.get(
            "/assets/flv.min.js"
        )

    assert response.status_code == 200
    assert "javascript" in response.headers[
        "content-type"
    ].lower()
    assert len(response.content) > 100000
