from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821

block_cipher = None

a = Analysis(
    [str(ROOT / "launch.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "static"), "static"),
        (str(ROOT / "data"),   "data"),
    ],
    hiddenimports=[
        "app",
        "app.fetch",
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
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.staticfiles",
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
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
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

app = BUNDLE(  # noqa: F821
    coll,
    name="IndustryNews.app",
    icon=None,
    bundle_identifier="com.industrynews.app",
    version="1.0.0",
    info_plist={
        "CFBundleName":               "Industry News",
        "CFBundleDisplayName":        "Industry News",
        "CFBundleVersion":            "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable":    True,
        "LSBackgroundOnly":           False,
        "LSEnvironment": {
            "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        },
    },
)
