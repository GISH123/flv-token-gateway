import threading
from pathlib import Path

import uvicorn

from .settings import Settings, get_settings


def run_http_gateway_server(settings: Settings) -> None:
    from .main import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.gateway_host,
        port=settings.gateway_http_port,
        log_level=settings.gateway_log_level,
    )


def run_https_gateway_server(
    settings: Settings,
    cert_file: Path,
    key_file: Path,
) -> None:
    from .main import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.gateway_host,
        port=settings.gateway_https_port,
        log_level=settings.gateway_log_level,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file),
    )


def run_server() -> None:
    cfg = get_settings()

    if not cfg.gateway_enable_http and not cfg.gateway_enable_https:
        raise RuntimeError(
            "At least one Gateway listener must be enabled."
        )

    cert_file = Path(cfg.tls_cert_file)
    key_file = Path(cfg.tls_key_file)

    if cfg.gateway_enable_https:
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

    if cfg.gateway_enable_http:
        print(
            f"HTTP Gateway      : "
            f"http://{cfg.gateway_host}:{cfg.gateway_http_port}"
        )
    else:
        print("HTTP Gateway      : disabled")

    if cfg.gateway_enable_https:
        print(
            f"HTTPS Gateway     : "
            f"https://{cfg.gateway_host}:{cfg.gateway_https_port}"
        )
    else:
        print("HTTPS Gateway     : disabled")

    print(f"Public base URL   : {cfg.public_base_url}")
    print(f"Upstream base URL : {cfg.upstream_base_url}")
    print(f"Token TTL         : {cfg.token_ttl_seconds} seconds")
    print(f"CORS origins      : {', '.join(cfg.cors_origins)}")

    if cfg.gateway_enable_https:
        print(f"TLS certificate   : {cert_file.resolve()}")
        print(f"TLS private key   : {key_file.resolve()}")

    print("Press CTRL+C to stop.")
    print("=" * 72)

    if cfg.gateway_enable_http and cfg.gateway_enable_https:
        http_thread = threading.Thread(
            target=run_http_gateway_server,
            args=(cfg,),
            daemon=True,
            name="flv-gateway-http",
        )
        http_thread.start()

        run_https_gateway_server(
            cfg,
            cert_file=cert_file,
            key_file=key_file,
        )
        return

    if cfg.gateway_enable_http:
        run_http_gateway_server(cfg)
        return

    run_https_gateway_server(
        cfg,
        cert_file=cert_file,
        key_file=key_file,
    )


if __name__ == "__main__":
    run_server()
