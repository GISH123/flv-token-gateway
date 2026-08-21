import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from app.settings import Settings


MOCK_FLV = b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00" + b"integration-test-payload"


def make_settings(**overrides):
    data = dict(
        public_base_url="http://gateway.test",
        upstream_base_url="http://upstream.test",
        token_secret="0123456789abcdef0123456789abcdef",
        token_ttl_seconds=300,
        token_issuer_api_key="",
        upstream_verify_tls=True,
    )
    data.update(overrides)
    return Settings(**data)


def upstream_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/dev/liveB03.flv":
        return httpx.Response(200, content=MOCK_FLV, headers={"content-type": "video/x-flv"})
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_no_token_is_denied():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(make_settings(), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        response = await client.get("/dev/liveB03.flv")
    await upstream.aclose()
    assert response.status_code == 401
    assert response.json()["detail"] == "token required"


@pytest.mark.asyncio
async def test_get_token_then_stream_succeeds():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(make_settings(), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        token_response = await client.post("/api/v1/tokens", json={"stream_path": "/dev/liveB03.flv"})
        assert token_response.status_code == 200
        data = token_response.json()
        assert data["expires_in"] == 300
        assert data["stream_url"].startswith("http://gateway.test/dev/liveB03.flv?token=")

        stream_response = await client.get(data["stream_url"])
        assert stream_response.status_code == 200
        assert stream_response.headers["content-type"].startswith("video/x-flv")
        assert stream_response.content == MOCK_FLV
    await upstream.aclose()


@pytest.mark.asyncio
async def test_token_for_one_path_cannot_open_another_path():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(make_settings(), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        data = (await client.post("/api/v1/tokens", json={"stream_path": "/dev/liveB03.flv"})).json()
        response = await client.get("/dev/liveB04.flv", params={"token": data["token"]})
    await upstream.aclose()
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_token_issuer_can_be_protected_by_api_key():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(make_settings(token_issuer_api_key="issuer-secret"), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        denied = await client.post("/api/v1/tokens", json={"stream_path": "/dev/liveB03.flv"})
        allowed = await client.post(
            "/api/v1/tokens",
            json={"stream_path": "/dev/liveB03.flv"},
            headers={"X-Token-API-Key": "issuer-secret"},
        )
    await upstream.aclose()
    assert denied.status_code == 401
    assert allowed.status_code == 200
