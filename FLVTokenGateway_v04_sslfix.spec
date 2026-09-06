# FLVTokenGateway_v04_sslfix.spec
# ------------------------------------------------------------
# Release build for FLV Token Gateway:
# - HTTP redirect listener: 18080
# - HTTPS Gateway listener: 18088
# - GET + POST token API
# - Bundled local FLV Player (/player)
# - Bundled local flv.js (/assets/flv.min.js)
# - External editable .env beside EXE
# - External TLS cert/key under certs/ beside EXE
#
# Build:
#   python -m PyInstaller --clean --noconfirm .\FLVTokenGateway_v04_sslfix.spec
# ------------------------------------------------------------

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import shutil
import sys
import textwrap
import _ssl

project_root = Path.cwd().resolve()
generated_dir = project_root / "build" / "_flv_gateway_v04_generated"
generated_dir.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# 1. Generate executable entrypoint.
# ------------------------------------------------------------
entry_source = r"""
from pathlib import Path
from urllib.parse import quote
import json
import os
import ssl
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.error
import urllib.request


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = runtime_dir()
os.chdir(BASE_DIR)


def run_server():
    # app.server owns both HTTP redirect and HTTPS Gateway listeners.
    from app.server import run_server as _run_server
    _run_server()


def _urlopen(req, timeout=8):
    # Test UI is a deployment helper. For a self-signed development certificate,
    # allow the operator to continue testing. Production browser validation must
    # still use a trusted certificate.
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if url.lower().startswith("https://"):
        context = ssl._create_unverified_context()
        return urllib.request.urlopen(req, timeout=timeout, context=context)
    return urllib.request.urlopen(req, timeout=timeout)


def run_test_ui():
    from app.settings import get_settings

    cfg = get_settings()

    root = tk.Tk()
    root.title("FLV Token Gateway - Test UI")
    root.geometry("940x670")
    root.minsize(840, 580)

    base_url = tk.StringVar(value=cfg.public_base_url)
    stream_path = tk.StringVar(value=cfg.test_stream_path)
    api_key = tk.StringVar(value="")
    status_text = tk.StringVar(value="Ready")
    expires_text = tk.StringVar(value="-")

    current = {"token": "", "stream_url": ""}

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)

    ttk.Label(
        outer,
        text="FLV Token Gateway Test UI",
        font=("Segoe UI", 16, "bold"),
    ).pack(anchor="w")

    ttk.Label(
        outer,
        text="HTTPS Health → GET Token → GET FLV header → Copy URL.",
    ).pack(anchor="w", pady=(2, 14))

    form = ttk.Frame(outer)
    form.pack(fill="x")

    ttk.Label(form, text="Gateway Base URL").grid(
        row=0, column=0, sticky="w", pady=4
    )
    ttk.Entry(form, textvariable=base_url, width=75).grid(
        row=0, column=1, sticky="ew", padx=(10, 0), pady=4
    )

    ttk.Label(form, text="Stream Path").grid(
        row=1, column=0, sticky="w", pady=4
    )
    ttk.Entry(form, textvariable=stream_path, width=75).grid(
        row=1, column=1, sticky="ew", padx=(10, 0), pady=4
    )

    ttk.Label(form, text="Token API Key (optional)").grid(
        row=2, column=0, sticky="w", pady=4
    )
    ttk.Entry(form, textvariable=api_key, width=75, show="*").grid(
        row=2, column=1, sticky="ew", padx=(10, 0), pady=4
    )

    form.columnconfigure(1, weight=1)

    result = tk.Text(
        outer,
        height=18,
        wrap="word",
        font=("Consolas", 10),
    )
    result.pack(fill="both", expand=True, pady=(14, 8))

    info = ttk.Frame(outer)
    info.pack(fill="x")

    ttk.Label(info, text="Status:").pack(side="left")
    ttk.Label(info, textvariable=status_text).pack(
        side="left", padx=(6, 20)
    )
    ttk.Label(info, text="Expires At:").pack(side="left")
    ttk.Label(info, textvariable=expires_text).pack(
        side="left", padx=(6, 0)
    )

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(12, 0))

    def log(message):
        result.insert("end", str(message) + "\n")
        result.see("end")

    def request_json(url):
        headers = {}
        if api_key.get().strip():
            headers["X-Token-API-Key"] = api_key.get().strip()

        req = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )

        try:
            with _urlopen(req, timeout=8) as response:
                payload = response.read()
                return response.status, json.loads(
                    payload.decode("utf-8")
                )
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                parsed = json.loads(payload.decode("utf-8"))
            except Exception:
                parsed = {
                    "detail": payload.decode(
                        "utf-8",
                        errors="replace",
                    )
                }
            return exc.code, parsed

    def do_health():
        status_text.set("Checking...")
        root.update_idletasks()

        try:
            status, data = request_json(
                base_url.get().rstrip("/") + "/health"
            )
            log(f"[HEALTH] HTTP {status}  {data}")
            status_text.set(f"Health HTTP {status}")
        except Exception as exc:
            log(f"[ERROR] health: {exc}")
            status_text.set("Health failed")

    def do_issue():
        status_text.set("Issuing token...")
        root.update_idletasks()

        try:
            path = stream_path.get().strip()
            url = (
                base_url.get().rstrip("/")
                + "/api/v1/tokens?stream_path="
                + quote(path, safe="")
            )

            status, data = request_json(url)

            log(f"[TOKEN GET] HTTP {status}")
            log(json.dumps(data, indent=2, ensure_ascii=False))

            if status == 200:
                current["token"] = str(data.get("token", ""))
                current["stream_url"] = str(
                    data.get("stream_url", "")
                )
                expires_text.set(
                    str(data.get("expires_at", "-"))
                )
                status_text.set("Token issued")
            else:
                status_text.set(f"Token HTTP {status}")

        except Exception as exc:
            log(f"[ERROR] token: {exc}")
            status_text.set("Token request failed")

    def do_stream_test():
        url = current.get("stream_url", "")

        if not url:
            messagebox.showinfo(
                "No token",
                "Issue a token first.",
            )
            return

        status_text.set("GET FLV...")
        root.update_idletasks()

        req = urllib.request.Request(
            url,
            method="GET",
        )

        try:
            with _urlopen(req, timeout=8) as response:
                prefix = response.read(3)
                log(
                    f"[STREAM GET] HTTP {response.status}, "
                    f"first 3 bytes={prefix!r}"
                )

                if (
                    response.status in (200, 206)
                    and prefix == b"FLV"
                ):
                    status_text.set("FLV GET PASS")
                else:
                    status_text.set(
                        f"Unexpected response: "
                        f"HTTP {response.status}"
                    )

        except urllib.error.HTTPError as exc:
            payload = exc.read()
            log(
                f"[STREAM GET] HTTP {exc.code}, "
                f"body={payload.decode('utf-8', errors='replace')}"
            )
            status_text.set(
                f"FLV GET HTTP {exc.code}"
            )

        except Exception as exc:
            log(f"[ERROR] FLV GET: {exc}")
            status_text.set("FLV GET failed")

    def do_copy():
        url = current.get("stream_url", "")

        if not url:
            messagebox.showinfo(
                "No URL",
                "Issue a token first.",
            )
            return

        root.clipboard_clear()
        root.clipboard_append(url)
        root.update()

        log("[COPY] stream_url copied to clipboard.")
        status_text.set("URL copied")

    ttk.Button(
        buttons,
        text="1. Health",
        command=do_health,
    ).pack(side="left", padx=(0, 8))

    ttk.Button(
        buttons,
        text="2. Issue Token (GET)",
        command=do_issue,
    ).pack(side="left", padx=8)

    ttk.Button(
        buttons,
        text="3. Test FLV GET",
        command=do_stream_test,
    ).pack(side="left", padx=8)

    ttk.Button(
        buttons,
        text="4. Copy Stream URL",
        command=do_copy,
    ).pack(side="left", padx=8)

    ttk.Button(
        buttons,
        text="Clear",
        command=lambda: result.delete("1.0", "end"),
    ).pack(side="right")

    log(f"Runtime directory: {BASE_DIR}")
    log(
        "Start FLVTokenGateway.exe first, "
        "then use this UI."
    )
    log(
        "Self-signed TLS is accepted by this Test UI only. "
        "Production browser validation still requires trust."
    )

    root.mainloop()


def main():
    if "--test-ui" in sys.argv:
        run_test_ui()
    else:
        run_server()


if __name__ == "__main__":
    main()
"""

entry_path = generated_dir / "flv_token_gateway_entry.py"
entry_path.write_text(
    textwrap.dedent(entry_source),
    encoding="utf-8",
)

# ------------------------------------------------------------
# 2. Generate helper launcher.
# ------------------------------------------------------------
test_ui_bat = generated_dir / "Open_Test_UI.bat"
test_ui_bat.write_text(
    '@echo off\r\n'
    'cd /d "%~dp0"\r\n'
    'start "" "%~dp0FLVTokenGateway.exe" --test-ui\r\n',
    encoding="utf-8",
)

# ------------------------------------------------------------
# 3. Runtime .env source.
# ------------------------------------------------------------
real_env = project_root / ".env"
example_env = project_root / ".env.example"
generated_env = generated_dir / ".env"

if real_env.exists():
    shutil.copy2(real_env, generated_env)
    print(f"[SPEC] Release .env source: {real_env}")
elif example_env.exists():
    shutil.copy2(example_env, generated_env)
    print(
        f"[SPEC] .env missing; release .env created from: "
        f"{example_env}"
    )
else:
    generated_env.write_text(
        "\n".join([
            "GATEWAY_HOST=0.0.0.0",
            "GATEWAY_HTTP_PORT=18080",
            "GATEWAY_HTTPS_PORT=18088",
            "GATEWAY_LOG_LEVEL=info",
            "PUBLIC_BASE_URL=https://127.0.0.1:18088",
            "UPSTREAM_BASE_URL=http://127.0.0.1:9090",
            "TOKEN_SECRET=replace-me-with-at-least-32-random-characters",
            "TOKEN_TTL_SECONDS=600",
            "TOKEN_ISSUER_API_KEY=",
            "UPSTREAM_VERIFY_TLS=true",
            "CORS_ALLOW_ORIGINS=*",
            "TEST_STREAM_PATH=/gishtest/gish.flv",
            "TLS_CERT_FILE=certs/gateway.crt",
            "TLS_KEY_FILE=certs/gateway.key",
            "",
        ]),
        encoding="utf-8",
    )
    print(
        "[SPEC] WARNING: generated default .env because "
        "no .env/.env.example was found."
    )

# ------------------------------------------------------------
# 4. Bundle web player assets into PyInstaller runtime.
#
# app.main resolves them from sys._MEIPASS/web when frozen.
# ------------------------------------------------------------
web_dir = project_root / "web"
player_html = web_dir / "player.html"
flv_js = web_dir / "flv.min.js"

if not player_html.is_file():
    raise SystemExit(
        f"[SPEC] Missing player asset: {player_html}"
    )

if not flv_js.is_file():
    raise SystemExit(
        f"[SPEC] Missing player asset: {flv_js}"
    )

datas = [
    (str(player_html), "web"),
    (str(flv_js), "web"),
]

print(f"[SPEC][WEB] include: {player_html}")
print(f"[SPEC][WEB] include: {flv_js}")

# ------------------------------------------------------------
# 5. OpenSSL runtime DLL collection.
# ------------------------------------------------------------
binaries = []

openssl_patterns = (
    "libssl*.dll",
    "libcrypto*.dll",
)

search_roots = []

for candidate in (
    Path(sys.base_prefix),
    Path(sys.prefix),
    Path(sys.executable).resolve().parent,
    Path(_ssl.__file__).resolve().parent,
):
    try:
        candidate = candidate.resolve()
    except Exception:
        pass

    if (
        candidate.exists()
        and candidate not in search_roots
    ):
        search_roots.append(candidate)

found_openssl = {}

for root in search_roots:
    candidate_dirs = [
        root,
        root / "DLLs",
        root / "Library" / "bin",
    ]

    for directory in candidate_dirs:
        if not directory.exists():
            continue

        for pattern in openssl_patterns:
            for dll in directory.glob(pattern):
                if dll.is_file():
                    found_openssl[
                        dll.name.lower()
                    ] = dll.resolve()

    for pattern in openssl_patterns:
        try:
            for dll in root.rglob(pattern):
                if not dll.is_file():
                    continue

                lower_parts = {
                    part.lower()
                    for part in dll.parts
                }

                if "site-packages" in lower_parts:
                    continue

                found_openssl.setdefault(
                    dll.name.lower(),
                    dll.resolve(),
                )

        except (OSError, PermissionError):
            pass

for dll in sorted(
    found_openssl.values(),
    key=lambda p: p.name.lower(),
):
    binaries.append((str(dll), "."))
    print(f"[SPEC][SSL] include: {dll}")

if not any(
    name.startswith("libssl")
    for name in found_openssl
):
    print(
        "[SPEC][SSL] WARNING: no libssl*.dll found."
    )

if not any(
    name.startswith("libcrypto")
    for name in found_openssl
):
    print(
        "[SPEC][SSL] WARNING: no libcrypto*.dll found."
    )

print(
    f"[SPEC][SSL] Python executable: "
    f"{sys.executable}"
)
print(
    f"[SPEC][SSL] sys.base_prefix : "
    f"{sys.base_prefix}"
)
print(
    f"[SPEC][SSL] _ssl module     : "
    f"{_ssl.__file__}"
)

# ------------------------------------------------------------
# 6. Hidden imports.
# ------------------------------------------------------------
hiddenimports = [
    "_ssl",
    "_hashlib",
    "app.main",
    "app.server",
    "app.settings",
    "app.token_service",
    "fastapi",
    "httpx",
    "pydantic",
    "pydantic_settings",
    "uvicorn",
    "uvicorn.config",
    "uvicorn.main",
    "uvicorn.server",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
]

a = Analysis(
    [str(entry_path)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FLVTokenGateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FLVTokenGateway",
)

# ------------------------------------------------------------
# 7. User-facing release files beside the EXE.
# ------------------------------------------------------------
release_dir = project_root / "dist" / "FLVTokenGateway"
release_dir.mkdir(parents=True, exist_ok=True)

copy_targets = [
    (generated_env, release_dir / ".env"),
    (test_ui_bat, release_dir / "Open_Test_UI.bat"),
]

if example_env.exists():
    copy_targets.append(
        (
            example_env,
            release_dir / ".env.example",
        )
    )

readme = project_root / "README.md"
if readme.exists():
    copy_targets.append(
        (
            readme,
            release_dir / "README.md",
        )
    )

for source, target in copy_targets:
    shutil.copy2(source, target)
    print(f"[SPEC] Release file: {target}")

docs_src = project_root / "docs"
docs_dst = release_dir / "docs"

if docs_src.exists():
    if docs_dst.exists():
        shutil.rmtree(docs_dst)

    shutil.copytree(docs_src, docs_dst)
    print(f"[SPEC] Release docs: {docs_dst}")

# TLS cert/key are deliberately NOT copied from source control.
# Create an empty deployment folder beside the EXE.
certs_dir = release_dir / "certs"
certs_dir.mkdir(parents=True, exist_ok=True)

print(f"[SPEC] TLS deployment dir: {certs_dir}")
print(
    "[SPEC] Place gateway.crt and gateway.key in certs/ "
    "before HTTPS runtime testing."
)
print(
    "[SPEC] Player URL after startup: "
    "<PUBLIC_BASE_URL>/player"
)
