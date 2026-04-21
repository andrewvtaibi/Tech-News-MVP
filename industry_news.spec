# industry_news.spec
# PyInstaller build spec for the Industry News desktop launcher.
#
# Usage (run once from the project root with venv active):
#   pip install pyinstaller
#   pyinstaller industry_news.spec
#
# Output:
#   dist/IndustryNews/              <- folder with all bundled files
#   dist/IndustryNews/IndustryNews.exe  <- the executable
#
# After building, run the Inno Setup script (installer/industry_news.iss)
# to produce a single-file Setup installer for distribution.

from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821  (SPECPATH is injected by PyInstaller)

block_cipher = None

a = Analysis(
    [str(ROOT / "launch.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Non-Python assets: HTML/CSS/JS frontend and ticker data file.
        # server/ and app/ are NOT listed here — PyInstaller bundles them
        # as compiled Python because launch.py imports them directly in
        # the frozen path (_start_server_frozen), which lets the analyser
        # follow the full import tree automatically.
        (str(ROOT / "static"), "static"),
        (str(ROOT / "data"),   "data"),
    ],
    hiddenimports=[
        # app.fetch is imported lazily (inside functions in news.py),
        # so the static analyser cannot detect it automatically.
        "app",
        "app.fetch",

        # uvicorn internals loaded dynamically at runtime
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",

        # starlette internals sometimes missed by the analyser
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.staticfiles",

        # other dependencies
        "slowapi",
        "slowapi.errors",
        "feedparser",
        "pydantic",
        "pydantic.deprecated.class_validators",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IndustryNews",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # console=True keeps the terminal window visible so users can read
    # startup progress and any error messages.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # replace with "installer/icon.ico" once you have one
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="IndustryNews",
)
