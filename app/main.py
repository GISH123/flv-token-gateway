from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit
import sys

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .settings import Settings, get_settings
from .token_service import TokenError, TokenExpired, issue_token, verify_token


class TokenRequest(BaseModel):
    stream_path: str = Field(examples=["/dev/liveB03.flv"])


class TokenResponse(BaseModel):
    token: str
    expires_in: int
    expires_at: int
    stream_url: str


def _make_http_client(settings: Settings) -> httpx.AsyncClient:
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
    return httpx.AsyncClient(
        timeout=timeout,
        verify=settings.upstream_verify_tls,
        follow_redirects=False,
    )


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def _resource_file(relative_path: str) -> Path:
    return _resource_root() / relative_path


def _public_base_for_request(
    request: Request,
    settings: Settings,
) -> str:
    """Return a client-visible base URL matching the request protocol."""
    configured = urlsplit(settings.public_base_url)
    host = configured.hostname or request.url.hostname

    if not host:
        return str(request.base_url).rstrip("/")

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    scheme = request.url.scheme.lower()

    if scheme == "http":
        port = settings.gateway_http_port
    elif scheme == "https":
        port = settings.gateway_https_port
    else:
        return str(request.base_url).rstrip("/")

    return f"{scheme}://{host}:{port}"


def create_app(
    settings: Settings | None = None,
    upstream_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    owns_client = upstream_client is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.upstream_client = upstream_client or _make_http_client(cfg)
        try:
            yield
        finally:
            if owns_client:
                await app.state.upstream_client.aclose()

    app = FastAPI(
        title="FLV Token Gateway",
        version="1.3.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Length", "Content-Range", "Accept-Ranges"],
    )

    app.state.settings = cfg
    if upstream_client is not None:
        app.state.upstream_client = upstream_client

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def issue_token_response(
        request: Request,
        stream_path: str,
        x_token_api_key: str | None,
    ) -> TokenResponse:
        if cfg.token_issuer_api_key and x_token_api_key != cfg.token_issuer_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token issuer API key",
            )

        try:
            token, claims = issue_token(
                path=stream_path,
                secret=cfg.token_secret,
                ttl_seconds=cfg.token_ttl_seconds,
            )
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        public_base = _public_base_for_request(request, cfg)
        stream_url = f"{public_base}{stream_path}?{urlencode({'token': token})}"

        return TokenResponse(
            token=token,
            expires_in=cfg.token_ttl_seconds,
            expires_at=claims.expires_at,
            stream_url=stream_url,
        )

    @app.get("/api/v1/tokens", response_model=TokenResponse)
    async def create_token_get(
        request: Request,
        stream_path: str = Query(...),
        x_token_api_key: str | None = Header(default=None),
    ) -> TokenResponse:
        return issue_token_response(
            request=request,
            stream_path=stream_path,
            x_token_api_key=x_token_api_key,
        )

    @app.post("/api/v1/tokens", response_model=TokenResponse)
    async def create_token_post(
        request: Request,
        body: TokenRequest,
        x_token_api_key: str | None = Header(default=None),
    ) -> TokenResponse:
        return issue_token_response(
            request=request,
            stream_path=body.stream_path,
            x_token_api_key=x_token_api_key,
        )

    @app.get("/player")
    async def player():
        player_file = _resource_file("web/player.html")
        if not player_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="player asset not found",
            )
        return FileResponse(
            player_file,
            media_type="text/html; charset=utf-8",
        )

    @app.get("/assets/flv.min.js")
    async def flv_js():
        flv_file = _resource_file("web/flv.min.js")
        if not flv_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="flv.js asset not found",
            )
        return FileResponse(
            flv_file,
            media_type="application/javascript; charset=utf-8",
        )

    @app.get("/{stream_path:path}")
    async def proxy_flv(
        stream_path: str,
        request: Request,
        token: str | None = Query(default=None),
    ):
        requested_path = "/" + stream_path

        if not requested_path.lower().endswith(".flv"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="not found",
            )

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token required",
            )

        try:
            verify_token(
                token=token,
                requested_path=requested_path,
                secret=cfg.token_secret,
            )
        except TokenExpired as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="token expired",
            ) from exc
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="invalid token",
            ) from exc

        passthrough_params = [
            (key, value)
            for key, value in request.query_params.multi_items()
            if key != "token"
        ]

        upstream_url = f"{cfg.upstream_base_url.rstrip('/')}{requested_path}"
        if passthrough_params:
            upstream_url += "?" + urlencode(passthrough_params)

        upstream_headers = {
            "Accept": request.headers.get("accept", "*/*"),
            "User-Agent": request.headers.get(
                "user-agent",
                "flv-token-gateway/1.3",
            ),
        }

        if request.headers.get("range"):
            upstream_headers["Range"] = request.headers["range"]

        client: httpx.AsyncClient = request.app.state.upstream_client
        upstream_request = client.build_request(
            "GET",
            upstream_url,
            headers=upstream_headers,
        )

        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="upstream unavailable",
            ) from exc

        if upstream.status_code >= 400:
            await upstream.aclose()
            return JSONResponse(
                status_code=upstream.status_code,
                content={"detail": "upstream rejected stream"},
            )

        async def body_iterator():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()

        headers = {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }

        for name in ("content-length", "content-range", "accept-ranges"):
            if name in upstream.headers:
                headers[name] = upstream.headers[name]

        return StreamingResponse(
            body_iterator(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get(
                "content-type",
                "video/x-flv",
            ),
            headers=headers,
        )

    return app


app = create_app()
