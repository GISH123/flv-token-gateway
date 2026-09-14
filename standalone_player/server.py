from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_CONFIG = {
    "local_host": "127.0.0.1",
    "local_port": 18100,
    "gateway_base_url": "https://10.2.192.9:18088",
    "stream_path": "/gishtest/gish.flv",
    "token_api_key": "",
    "open_browser": True,
}


def resource_dir() -> Path:
    """Bundled read-only assets (player.html / flv.min.js)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def runtime_dir() -> Path:
    """Editable runtime files live beside the EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_config() -> dict:
    path = runtime_dir() / "player_config.json"
    cfg = dict(DEFAULT_CONFIG)

    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        if not isinstance(user_cfg, dict):
            raise ValueError("player_config.json must contain a JSON object")
        cfg.update(user_cfg)

    return cfg


class PlayerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, config: dict, **kwargs):
        self.player_config = config
        super().__init__(*args, directory=str(resource_dir()), **kwargs)

    def do_GET(self):
        if self.path in ("", "/"):
            self.path = "/player.html"

        if self.path == "/config.json":
            payload = {
                "gateway_base_url": self.player_config["gateway_base_url"],
                "stream_path": self.player_config["stream_path"],
                "token_api_key": self.player_config.get("token_api_key", ""),
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt: str, *args):
        print(f"[PLAYER] {self.client_address[0]} - {fmt % args}")


def main() -> int:
    cfg = load_config()

    host = str(cfg.get("local_host", "127.0.0.1"))
    port = int(cfg.get("local_port", 18100))
    open_browser = bool(cfg.get("open_browser", True))

    # Security / deployment rule: this player is intended to be local-only.
    if host not in ("127.0.0.1", "localhost"):
        print(
            f"[WARNING] local_host={host!r}. "
            "Recommended value is 127.0.0.1 so the Player is not exposed on the LAN."
        )

    handler_factory = lambda *args, **kwargs: PlayerHandler(
        *args, config=cfg, **kwargs
    )

    server = ThreadingHTTPServer((host, port), handler_factory)
    server.daemon_threads = True
    server.allow_reuse_address = True

    url = f"http://{host}:{port}/"

    print("=" * 72)
    print("FLV Token Standalone Player")
    print(f"Runtime config : {runtime_dir() / 'player_config.json'}")
    print(f"Local player   : {url}")
    print(f"Gateway        : {cfg['gateway_base_url']}")
    print(f"Stream path    : {cfg['stream_path']}")
    print("Expected route : Player -> Gateway only (Origin must not be configured here)")
    print("Press CTRL+C to stop.")
    print("=" * 72)

    if open_browser:
        def _open():
            time.sleep(0.6)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping FLV Token Standalone Player...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
