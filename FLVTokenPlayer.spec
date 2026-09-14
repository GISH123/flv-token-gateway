# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import shutil

# Build from the directory that contains this .spec file.
project_root = Path(SPECPATH).resolve()
player_dir = project_root / "standalone_player"
dist_dir = project_root / "dist" / "FLVTokenPlayer"

runtime_config = player_dir / "player_config.json"
example_config = player_dir / "player_config.example.json"

required_files = [
    player_dir / "server.py",
    player_dir / "player.html",
    player_dir / "flv.min.js",
    example_config,
]

missing = [str(path) for path in required_files if not path.is_file()]
if missing:
    raise SystemExit(
        "Missing standalone player files:\n  " + "\n  ".join(missing)
    )

# Local/runtime config is intentionally not tracked in Git.
# If it exists, package that deployment config beside the EXE.
# Otherwise, fall back to the public/example config so a fresh clone can build.
config_source = runtime_config if runtime_config.is_file() else example_config

a = Analysis(
    [str(player_dir / "server.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(player_dir / "player.html"), "."),
        (str(player_dir / "flv.min.js"), "."),
    ],
    hiddenimports=[],
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
    name="FLVTokenPlayer",
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
    name="FLVTokenPlayer",
)

# Keep player_config.json external and editable beside FLVTokenPlayer.exe.
# This preserves the separation:
#   Player -> Gateway
# while Origin configuration remains Gateway-only.
dist_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(config_source, dist_dir / "player_config.json")
