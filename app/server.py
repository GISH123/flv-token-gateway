import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from .settings import get_settings


def create_http_redirect_app(public_base_url: str) -> FastAPI:
    """
    HTTP listener used only to redirect clients to the HTTPS Gateway.
    """
    redirect_app = FastAPI(
        title="FLV Token Gateway HTTP Redirect",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    https_base = public_base_url.rstrip("/")

    @redirect_app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def redirect_to_https(path: str, request: Request):
        target = f"{https_base}/{path}"

        if request.url.query:
            target += f"?{request.url.query}"

        return RedirectResponse(
            url=target,
            status_code=308,
        )

    return redirect_app


def run_http_redirect_server(
    host: str,
    port: int,
    public_base_url: str,
    log_level: str,
) -> None:
    redirect_app = create_http_redirect_app(public_base_url)

    uvicorn.run(
        redirect_app,
        host=host,
        port=port,
        log_level=log_level,
    )


def run_server() -> None:
    cfg = get_settings()

    from .main import app

    cert_file = Path(cfg.tls_cert_file)
    key_file = Path(cfg.tls_key_file)

    if not cert_file.is_file():
        raise RuntimeError(
            f"TLS certificate not found: {cert_file.resolve()}"
        )

    if not key_file.is_file():
        raise RuntimeError(
            f"TLS private key not found: {key_file.resolve()}"
        )

    print("=" * 72)
    print("FLV Token Gateway")
    print(
        f"HTTP redirect     : "
        f"http://{cfg.gateway_host}:{cfg.gateway_http_port}"
    )
    print(
        f"HTTPS Gateway     : "
        f"https://{cfg.gateway_host}:{cfg.gateway_https_port}"
    )
    print(f"Public base URL   : {cfg.public_base_url}")
    print(f"Upstream base URL : {cfg.upstream_base_url}")
    print(f"Token TTL         : {cfg.token_ttl_seconds} seconds")
    print(f"CORS origins      : {', '.join(cfg.cors_origins)}")
    print(f"TLS certificate   : {cert_file.resolve()}")
    print(f"TLS private key   : {key_file.resolve()}")
    print("Press CTRL+C to stop.")
    print("=" * 72)

    redirect_thread = threading.Thread(
        target=run_http_redirect_server,
        kwargs={
            "host": cfg.gateway_host,
            "port": cfg.gateway_http_port,
            "public_base_url": cfg.public_base_url,
            "log_level": cfg.gateway_log_level,
        },
        daemon=True,
        name="flv-gateway-http-redirect",
    )
    redirect_thread.start()

    uvicorn.run(
        app,
        host=cfg.gateway_host,
        port=cfg.gateway_https_port,
        log_level=cfg.gateway_log_level,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file),
    )


if __name__ == "__main__":
    run_server()