# PyInstaller spec — produces dist/FaroAI/ on Windows (and on Mac/Linux
# if anyone wants a non-py2app build path).
#
# Run via packaging/build_windows.ps1 (which sets up the build venv +
# invokes pyinstaller). Don't run pyinstaller directly without that
# script — it expects the working directory to be the project root.
#
# Bundle composition mirrors setup_py2app.py:
#   - Pinned Python 3.12 (vendored by PyInstaller)
#   - All three LLM provider SDKs: anthropic, openai, google-genai
#   - FastAPI + uvicorn + pywebview + httpx
#   - Our code (core, api, mcp_server) + frontend (web/out)
#   - Resources: FAROAI.md, .claude/skills/, prompts/, config/
#
# We use --onedir mode (this spec produces a directory, not a single
# .exe) because --onefile re-extracts to a temp dir on every launch
# (~3s of friction the user feels). NSIS wraps the directory in a
# normal Setup.exe afterward.
#
# PyInstaller is much better than py2app at namespace packages
# (PEP 420), so google.* doesn't need the post-build copy hack
# setup_py2app.py needs — `--collect-all google` here just works.

# pylint: disable=invalid-name,unused-variable

from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).resolve().parent

# Read version from core/__init__.py (single source of truth).
# Looks for `_BUNDLED_VERSION = "..."` — runtime `__version__` resolves
# from the overlay manifest, but the bundled .exe's CFBundleVersion /
# FileVersion needs the static fallback we baked into core/__init__.py.
__version__ = "0.2.0"
for _line in (PROJECT_ROOT / "core" / "__init__.py").read_text().splitlines():
    if _line.strip().startswith("_BUNDLED_VERSION"):
        __version__ = _line.split("=", 1)[1].strip().strip('"').strip("'")
        break


# Static resources copied into the bundle. Each (src, dest_subdir).
# In source mode `core.paths.resource_path("foo")` resolves to
# PROJECT_ROOT/foo/; in the PyInstaller bundle, sys._MEIPASS/foo/.
# Same code reads both transparently.
datas = [
    (str(PROJECT_ROOT / "web" / "out"), "web/out"),
    (str(PROJECT_ROOT / "FAROAI.md"), "."),
    (str(PROJECT_ROOT / ".claude" / "skills"), ".claude/skills"),
    (str(PROJECT_ROOT / "prompts"), "prompts"),
    (str(PROJECT_ROOT / "config"), "config"),
]


# Hidden imports — modules PyInstaller's static analyzer misses
# because they're imported dynamically. FastAPI uses dynamic imports
# heavily for its routing system; Pydantic v2 has plugin loading
# patterns that PyInstaller can miss; uvicorn loads workers by name.
hiddenimports = [
    # Backend stack — dynamic import surface
    "uvicorn",
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
    "fastapi",
    "starlette",
    "sse_starlette",
    "pydantic",
    "pydantic_core",
    # HTTP + auth
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    # Our code (paranoid-explicit so a future refactor doesn't break
    # the bundle silently)
    "api",
    "api.main",
    "core",
    "core.desktop",
    "core.paths",
    "core.overlay",
    "core.connectors",
    "core.connectors.chartmetric",
    "core.connectors.spotify",
    "core.connectors.youtube",
    "core.llm",
    "core.llm.anthropic_provider",
    "core.llm.openai_provider",
    "core.llm.gemini_provider",
    "core.updater",
    "mcp_server",
    "mcp_server.server",
    "mcp_server.tools.composite_evaluate",
    "mcp_server.tools.composite_similar",
]


# Collect_all() must run BEFORE Analysis(): it returns (datas, binaries,
# hiddenimports) as 2-tuple lists which Analysis's __init__ converts
# to its internal 3-tuple TOC format. Calling collect_all + a.datas +=
# AFTER Analysis runs mixes 2- and 3-tuples in the same list and crashes
# COLLECT() with "not enough values to unpack" — exactly what bit the
# first Windows CI run.
from PyInstaller.utils.hooks import collect_all  # noqa: E402

extra_datas, extra_binaries, extra_hidden = [], [], []
for _pkg in ("google", "grpc", "anthropic", "openai"):
    try:
        _d, _b, _h = collect_all(_pkg)
        extra_datas += _d
        extra_binaries += _b
        extra_hidden += _h
    except Exception:
        # Skip if not installed (e.g. grpc isn't pulled by google-genai
        # 1.75+). Failure here just means the package isn't bundled —
        # caller would see a clean ImportError if they actually need it.
        pass

# Analysis: PyInstaller walks imports starting from the entry point.
a = Analysis(
    [str(PROJECT_ROOT / "core" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=extra_binaries,
    datas=datas + extra_datas,
    hiddenimports=hiddenimports + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Same exclude list as setup_py2app.py — drops ~150 MB of cruft
    # (numpy, pandas, scipy, matplotlib, etc.) PyInstaller's walker
    # would otherwise auto-pull on the slim chance they're imported
    # transitively.
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "tkinter",
        "PIL",
        "pillow",
        "sphinx",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "pytest_asyncio",
        "py.test",
        # Note: NOT excluding `wheel` here. PyInstaller's setuptools
        # hook aliases `wheel` internally (vendored under
        # _pyinstaller_hooks_contrib); excluding it crashes
        # Analysis with "Target module 'wheel' already imported
        # as ExcludedModule". Same applies to `setuptools` itself.
        "test",
        "tests",
        "docutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# The exe is the launcher binary inside the onedir bundle.
# console=False because Windows would otherwise pop up a Command Prompt
# alongside the chromeless window — exactly the UX we don't want.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaroAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX off until we verify it doesn't trigger AV false positives
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Branded Windows icon. PyInstaller embeds it into FaroAI.exe so
    # the file shows the right icon in Explorer + the NSIS installer
    # propagates it to the Start Menu and Desktop shortcuts (via
    # CreateShortcut's -i argument referencing the .exe).
    icon=str(PROJECT_ROOT / "packaging" / "FaroAI.ico"),
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FaroAI",
)
