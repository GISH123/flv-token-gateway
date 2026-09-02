import uvicorn

from .settings import get_settings


def run_server() -> None:
    cfg = get_settings()

    from .main import app

    print("=" * 68)
    print("FLV Token Gateway")
    print(f"Listen address    : http://{cfg.gateway_host}:{cfg.gateway_port}")
    print(f"Public base URL   : {cfg.public_base_url}")
    print(f"Upstream base URL : {cfg.upstream_base_url}")
    print(f"CORS origins      : {', '.join(cfg.cors_origins)}")
    print("Press CTRL+C to stop.")
    print("=" * 68)

    uvicorn.run(
        app,
        host=cfg.gateway_host,
        port=cfg.gateway_port,
        log_level=cfg.gateway_log_level,
    )


if __name__ == "__main__":
    run_server()
