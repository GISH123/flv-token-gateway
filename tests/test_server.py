import httpx
import pytest

from app.server import create_http_redirect_app


@pytest.mark.asyncio
async def test_http_redirect_preserves_path_and_query():
    app = create_http_redirect_app(
        "https://10.2.192.9:18088"
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
        follow_redirects=False,
    ) as client:
        response = await client.get(
            "/gishtest/gish.flv?token=abc123"
        )

    assert response.status_code == 308
    assert response.headers["location"] == (
        "https://10.2.192.9:18088/"
        "gishtest/gish.flv?token=abc123"
    )


@pytest.mark.asyncio
async def test_http_redirect_health():
    app = create_http_redirect_app(
        "https://10.2.192.9:18088"
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 308
    assert response.headers["location"] == (
        "https://10.2.192.9:18088/health"
    )