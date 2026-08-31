# FLVTokenGateway_v04_sslfix.spec
# ------------------------------------------------------------
# Release-oriented one-command build for FLV Token Gateway.
#
# Run from repository root:
#   python -m PyInstaller --clean --noconfirm FLVTokenGateway_v04_sslfix.spec
#
# Final layout:
#   dist/FLVTokenGateway/
#       FLVTokenGateway.exe
#       .env
#       .env.example            (if repo has it)
#       Open_Test_UI.bat
#       README.md               (if repo has it)
#       docs/                   (if repo has it)
#       _internal/              (PyInstaller runtime dependencies)
#
# IMPORTANT:
# - .env is intentionally EXTERNAL and EDITABLE beside the EXE.
# - The real .env is copied into dist only at build time; keep it gitignored.
# - PyInstaller 6 keeps supporting runtime files in _internal by default.
#   This spec deliberately post-copies deployment/user-facing files beside the EXE.
# ------------------------------------------------------------

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import shutil
import textwrap
import sys
import _ssl

project_root = Path.cwd().resolve()
generated_dir = project_root / "build" / "_flv_gateway_v04_generated"
generated_dir.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# 1. Generate executable entrypoint at build time.
# ------------------------------------------------------------
entry_source = r"""
from pathlib import Path
import json
import os
import sys
import urllib.error
import urllib.request


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = runtime_dir()

# app.settings uses env_file=".env"; therefore load config relative to EXE folder.
os.chdir(BASE_DIR)


def run_server():
    # Import after chdir so external .env beside EXE is used.
    from app.main import app
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "18088"))
    log_level = os.getenv("GATEWAY_LOG_LEVEL", "info")

    print("=" * 68)
    print("FLV Token Gateway")
    print(f"Working directory : {BASE_DIR}")
    print(f"Config file       : {BASE_DIR / '.env'}")
    print(f"Listen address    : http://{host}:{port}")
    print(f"Health check      : http://{host}:{port}/health")
    print("Press CTRL+C to stop.")
    print("=" * 68)

    uvicorn.run(app, host=host, port=port, log_level=log_level)


def run_test_ui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("FLV Token Gateway - Test UI")
    root.geometry("920x650")
    root.minsize(820, 560)

    base_url = tk.StringVar(value="http://127.0.0.1:18088")
    stream_path = tk.StringVar(value="/gishtest/gish.flv")
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
        text="Health → Issue Token → GET FLV header → Copy URL to VLC.",
    ).pack(anchor="w", pady=(2, 14))

    form = ttk.Frame(outer)
    form.pack(fill="x")

    ttk.Label(form, text="Gateway Base URL").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(form, textvariable=base_url, width=75).grid(
        row=0, column=1, sticky="ew", padx=(10, 0), pady=4
    )

    ttk.Label(form, text="Stream Path").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(form, textvariable=stream_path, width=75).grid(
        row=1, column=1, sticky="ew", padx=(10, 0), pady=4
    )

    ttk.Label(form, text="Token API Key (optional)").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Entry(form, textvariable=api_key, width=75, show="*").grid(
        row=2, column=1, sticky="ew", padx=(10, 0), pady=4
    )
    form.columnconfigure(1, weight=1)

    result = tk.Text(outer, height=18, wrap="word", font=("Consolas", 10))
    result.pack(fill="both", expand=True, pady=(14, 8))

    info = ttk.Frame(outer)
    info.pack(fill="x")
    ttk.Label(info, text="Status:").pack(side="left")
    ttk.Label(info, textvariable=status_text).pack(side="left", padx=(6, 20))
    ttk.Label(info, text="Expires At:").pack(side="left")
    ttk.Label(info, textvariable=expires_text).pack(side="left", padx=(6, 0))

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(12, 0))

    def log(message):
        result.insert("end", str(message) + "\n")
        result.see("end")

    def request_json(url, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if api_key.get().strip():
            headers["X-Token-API-Key"] = api_key.get().strip()

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = response.read()
                return response.status, json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                parsed = json.loads(payload.decode("utf-8"))
            except Exception:
                parsed = {"detail": payload.decode("utf-8", errors="replace")}
            return exc.code, parsed

    def do_health():
        status_text.set("Checking...")
        root.update_idletasks()
        try:
            status, data = request_json(base_url.get().rstrip("/") + "/health")
            log(f"[HEALTH] HTTP {status}  {data}")
            status_text.set(f"Health HTTP {status}")
        except Exception as exc:
            log(f"[ERROR] health: {exc}")
            status_text.set("Health failed")

    def do_issue():
        status_text.set("Issuing token...")
        root.update_idletasks()
        try:
            status, data = request_json(
                base_url.get().rstrip("/") + "/api/v1/tokens",
                method="POST",
                body={"stream_path": stream_path.get().strip()},
            )
            log(f"[TOKEN] HTTP {status}")
            log(json.dumps(data, indent=2, ensure_ascii=False))
            if status == 200:
                current["token"] = str(data.get("token", ""))
                current["stream_url"] = str(data.get("stream_url", ""))
                expires_text.set(str(data.get("expires_at", "-")))
                status_text.set("Token issued")
            else:
                status_text.set(f"Token HTTP {status}")
        except Exception as exc:
            log(f"[ERROR] token: {exc}")
            status_text.set("Token request failed")

    def do_stream_test():
        url = current.get("stream_url", "")
        if not url:
            messagebox.showinfo("No token", "Issue a token first.")
            return

        status_text.set("GET FLV...")
        root.update_idletasks()

        # This is a real HTTP GET. Read only the FLV signature to avoid consuming
        # an endless live stream.
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                prefix = response.read(3)
                log(f"[STREAM GET] HTTP {response.status}, first 3 bytes={prefix!r}")
                if response.status == 200 and prefix == b"FLV":
                    status_text.set("FLV GET PASS")
                else:
                    status_text.set(f"Unexpected response: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            log(
                f"[STREAM GET] HTTP {exc.code}, "
                f"body={payload.decode('utf-8', errors='replace')}"
            )
            status_text.set(f"FLV GET HTTP {exc.code}")
        except Exception as exc:
            log(f"[ERROR] FLV GET: {exc}")
            status_text.set("FLV GET failed")

    def do_copy():
        url = current.get("stream_url", "")
        if not url:
            messagebox.showinfo("No URL", "Issue a token first.")
            return
        root.clipboard_clear()
        root.clipboard_append(url)
        root.update()
        log("[COPY] stream_url copied to clipboard.")
        status_text.set("URL copied")

    ttk.Button(buttons, text="1. Health", command=do_health).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="2. Issue Token", command=do_issue).pack(side="left", padx=8)
    ttk.Button(buttons, text="3. Test FLV GET", command=do_stream_test).pack(side="left", padx=8)
    ttk.Button(buttons, text="4. Copy Stream URL", command=do_copy).pack(side="left", padx=8)
    ttk.Button(buttons, text="Clear", command=lambda: result.delete("1.0", "end")).pack(
        side="right"
    )

    log(f"Runtime directory: {BASE_DIR}")
    log("Start FLVTokenGateway.exe first, then use this UI.")
    log("Test FLV GET reads only the first 3 bytes and expects b'FLV'.")

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
entry_path.write_text(textwrap.dedent(entry_source), encoding="utf-8")

# ------------------------------------------------------------
# 2. Generate user-facing helper launcher.
# ------------------------------------------------------------
test_ui_bat = generated_dir / "Open_Test_UI.bat"
test_ui_bat.write_text(
    '@echo off\r\n'
    'cd /d "%~dp0"\r\n'
    'start "" "%~dp0FLVTokenGateway.exe" --test-ui\r\n',
    encoding="utf-8",
)

# ------------------------------------------------------------
# 3. Resolve the runtime .env source.
# ------------------------------------------------------------
real_env = project_root / ".env"
example_env = project_root / ".env.example"

generated_env = generated_dir / ".env"
if real_env.exists():
    shutil.copy2(real_env, generated_env)
    print(f"[SPEC] Release .env source: {real_env}")
elif example_env.exists():
    shutil.copy2(example_env, generated_env)
    print(f"[SPEC] .env missing; release .env created from: {example_env}")
else:
    generated_env.write_text(
        "\n".join([
            "PUBLIC_BASE_URL=http://127.0.0.1:18088",
            "UPSTREAM_BASE_URL=http://127.0.0.1:9090",
            "TOKEN_SECRET=replace-me-with-at-least-32-random-characters",
            "TOKEN_TTL_SECONDS=300",
            "TOKEN_ISSUER_API_KEY=",
            "UPSTREAM_VERIFY_TLS=true",
            "",
        ]),
        encoding="utf-8",
    )
    print("[SPEC] WARNING: generated default .env because no .env/.env.example was found.")

# ------------------------------------------------------------
# 4. Only PyInstaller runtime dependencies are bundled as datas.
#    User-editable delivery files are copied AFTER COLLECT to the top level.
# ------------------------------------------------------------
datas = []

# ------------------------------------------------------------
# 4a. Explicitly collect OpenSSL DLLs required by Python's _ssl/_hashlib.
#
# Some Windows Python/venv layouts do not let PyInstaller discover these
# dependent DLLs automatically. The EXE can therefore build successfully but
# fail at runtime with:
#   ImportError: DLL load failed while importing _ssl
#
# Search the base Python installation / venv / _ssl location and add matching
# libssl/libcrypto DLLs as binary dependencies.
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
    if candidate.exists() and candidate not in search_roots:
        search_roots.append(candidate)

found_openssl = {}

for root in search_roots:
    # Common official-CPython / Conda locations first.
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
                    found_openssl[dll.name.lower()] = dll.resolve()

    # Small recursive fallback for unusual Python layouts.
    # Skip site-packages where possible to avoid unrelated vendor DLL copies.
    for pattern in openssl_patterns:
        try:
            for dll in root.rglob(pattern):
                if not dll.is_file():
                    continue
                lower_parts = {part.lower() for part in dll.parts}
                if "site-packages" in lower_parts:
                    continue
                found_openssl.setdefault(dll.name.lower(), dll.resolve())
        except (OSError, PermissionError):
            pass

for dll in sorted(found_openssl.values(), key=lambda p: p.name.lower()):
    binaries.append((str(dll), "."))
    print(f"[SPEC][SSL] include: {dll}")

if not any(name.startswith("libssl") for name in found_openssl):
    print("[SPEC][SSL] WARNING: no libssl*.dll found.")
if not any(name.startswith("libcrypto") for name in found_openssl):
    print("[SPEC][SSL] WARNING: no libcrypto*.dll found.")

print(f"[SPEC][SSL] Python executable: {sys.executable}")
print(f"[SPEC][SSL] sys.base_prefix : {sys.base_prefix}")
print(f"[SPEC][SSL] _ssl module     : {_ssl.__file__}")

hiddenimports = [
    "_ssl",
    "_hashlib",
    "app.main",
    "app.settings",
    "app.token_service",
    "uvicorn",
    "uvicorn.config",
    "uvicorn.main",
    "uvicorn.server",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "h11",
    "httpx",
    "httpcore",
    "pydantic",
    "pydantic_settings",
    "dotenv",
    "tkinter",
    "tkinter.ttk",
    "_tkinter",
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
    excludes=["pytest", "tests"],
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
# 5. POST-BUILD: copy user-facing files BESIDE the EXE.
#    PyInstaller 6 normally places supporting data under _internal, so doing
#    this explicitly guarantees .env / test UI / docs are visible at top level.
# ------------------------------------------------------------
release_dir = Path(DISTPATH) / "FLVTokenGateway"
release_dir.mkdir(parents=True, exist_ok=True)

shutil.copy2(generated_env, release_dir / ".env")
shutil.copy2(test_ui_bat, release_dir / "Open_Test_UI.bat")

if example_env.exists():
    shutil.copy2(example_env, release_dir / ".env.example")

readme = project_root / "README.md"
if readme.exists():
    shutil.copy2(readme, release_dir / "README.md")

docs_src = project_root / "docs"
docs_dst = release_dir / "docs"
if docs_src.exists():
    if docs_dst.exists():
        shutil.rmtree(docs_dst)
    shutil.copytree(docs_src, docs_dst)

# Also collect final handoff docs placed in repo root.
root_docs = []
for pattern in (
    "FLV_Token_Gateway_*.md",
    "FLV_Token_Gateway_*.pptx",
    "FLV_Token_Gateway_*.docx",
):
    root_docs.extend(project_root.glob(pattern))

if root_docs:
    docs_dst.mkdir(parents=True, exist_ok=True)
    for p in root_docs:
        if p.is_file():
            shutil.copy2(p, docs_dst / p.name)

print("[SPEC] Release files copied beside EXE:")
print(f"       {release_dir / '.env'}")
print(f"       {release_dir / 'Open_Test_UI.bat'}")
if example_env.exists():
    print(f"       {release_dir / '.env.example'}")
if readme.exists():
    print(f"       {release_dir / 'README.md'}")
if docs_dst.exists():
    print(f"       {docs_dst}")
