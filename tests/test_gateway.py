import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from app.settings import Settings


MOCK_FLV = b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00" + b"integration-test-payload"


def make_settings(**overrides):
    data = dict(
        gateway_host="0.0.0.0",
        gateway_port=18088,
        gateway_log_level="info",
        public_base_url="http://gateway.test",
        upstream_base_url="http://upstream.test",
        token_secret="0123456789abcdef0123456789abcdef",
        token_ttl_seconds=300,
        token_issuer_api_key="",
        upstream_verify_tls=True,
        cors_allow_origins="*",
        test_stream_path="/gishtest/gish.flv",
    )
    data.update(overrides)
    return Settings(**data)


class MockAsyncStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield MOCK_FLV


def upstream_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/dev/liveB03.flv":
        headers = {"content-type": "video/x-flv", "accept-ranges": "bytes"}
        if request.headers.get("range"):
            headers["content-range"] = "bytes 0-2/36"
            return httpx.Response(206, stream=MockAsyncStream(), headers=headers)
        return httpx.Response(200, stream=MockAsyncStream(), headers=headers)
    return httpx.Response(404, stream=MockAsyncStream())


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


@pytest.mark.asyncio
async def test_cors_allows_browser_player_by_default():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(make_settings(), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        response = await client.options(
            "/dev/liveB03.flv",
            headers={
                "Origin": "http://10.2.192.8:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
    await upstream.aclose()
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.asyncio
async def test_cors_can_be_restricted_to_configured_origin():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(
        make_settings(cors_allow_origins="http://10.2.192.8:8080,http://player.test"),
        upstream_client=upstream,
    )
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        allowed = await client.options(
            "/dev/liveB03.flv",
            headers={
                "Origin": "http://10.2.192.8:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/dev/liveB03.flv",
            headers={
                "Origin": "http://not-allowed.test",
                "Access-Control-Request-Method": "GET",
            },
        )
    await upstream.aclose()
    assert allowed.headers["access-control-allow-origin"] == "http://10.2.192.8:8080"
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_range_header_is_forwarded_for_browser_players():
    seen = {}

    def range_upstream_handler(request: httpx.Request) -> httpx.Response:
        seen["range"] = request.headers.get("range")
        return upstream_handler(request)

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(range_upstream_handler))
    app = create_app(make_settings(), upstream_client=upstream)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
        data = (await client.post("/api/v1/tokens", json={"stream_path": "/dev/liveB03.flv"})).json()
        response = await client.get(data["stream_url"], headers={"Range": "bytes=0-"})
    await upstream.aclose()
    assert seen["range"] == "bytes=0-"
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-2/36"
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.asyncio
async def test_token_response_does_not_expose_upstream_origin():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(
        make_settings(
            public_base_url="http://gateway.test",
            upstream_base_url="https://10.2.192.8:8088",
        ),
        upstream_client=upstream,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
    ) as client:
        response = await client.post(
            "/api/v1/tokens",
            json={"stream_path": "/dev/liveB03.flv"},
        )

    await upstream.aclose()
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"token", "expires_in", "expires_at", "stream_url"}
    assert data["stream_url"].startswith("http://gateway.test/")
    assert "10.2.192.8" not in response.text
    assert "https://10.2.192.8:8088" not in response.text


@pytest.mark.asyncio
async def test_upstream_rejection_does_not_expose_upstream_origin():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = create_app(
        make_settings(upstream_base_url="https://10.2.192.8:8088"),
        upstream_client=upstream,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
    ) as client:
        token_data = (
            await client.post(
                "/api/v1/tokens",
                json={"stream_path": "/dev/missing.flv"},
            )
        ).json()
        response = await client.get(token_data["stream_url"])

    await upstream.aclose()
    assert response.status_code == 404
    assert response.json() == {"detail": "upstream rejected stream"}
    assert "10.2.192.8" not in response.text
    assert "8088" not in response.text
