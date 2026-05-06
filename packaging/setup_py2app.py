"""py2app build config — produces ``dist/FaroAI.app`` from ``core/__main__.py``.

Run via ``packaging/build_mac.sh`` (which creates the build venv +
sets the working directory). Don't run ``python setup_py2app.py``
directly from the repo root — py2app expects to be invoked from a
clean state.

Bundle composition (target ~400 MB):
  - Pinned Python 3.12 framework (vendored by py2app)
  - All three LLM provider SDKs: anthropic, openai, google-genai
  - FastAPI + uvicorn + pywebview + httpx
  - Our code (core, api, mcp_server) + frontend (web/out)
  - Resources: FAROAI.md, .claude/skills/, prompts/, config/

Aggressive excludes drop the ~150 MB of cruft py2app's dependency
walker would otherwise auto-pull (numpy, pandas, scipy, matplotlib,
tkinter, sphinx, IPython, etc.) — none of which we actually use.
"""
from pathlib import Path

from setuptools import setup

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Read version from core/__init__.py — single source of truth.
VERSION = "0.2.0"
for line in (PROJECT_ROOT / "core" / "__init__.py").read_text().splitlines():
    if line.strip().startswith("__version__"):
        VERSION = line.split("=", 1)[1].strip().strip('"').strip("'")
        break


APP = [str(PROJECT_ROOT / "core" / "__main__.py")]

# Resources copied as-is into Contents/Resources/. The frontend, the
# editable persona file, the bundled skill defaults, prompts, and config
# YAMLs all live here. resource_path() in core/paths.py finds them at
# runtime via sys.executable's parent.
DATA_FILES = [
    ("web/out", [str(PROJECT_ROOT / "web" / "out")]),
    ("FAROAI.md", [str(PROJECT_ROOT / "FAROAI.md")]),
    (".claude/skills", [str(PROJECT_ROOT / ".claude" / "skills")]),
    ("prompts", [str(PROJECT_ROOT / "prompts")]),
    ("config", [str(PROJECT_ROOT / "config")]),
]

# Packages py2app must include explicitly — its dependency walker
# misses dynamic imports (FastAPI uses them everywhere) and provider
# SDKs that lazy-load submodules.
PACKAGES = [
    # LLM provider SDKs (Anthropic + OpenAI; Gemini handled via
    # `includes` below since it lives under the `google` PEP-420
    # namespace package which py2app's old find_module can't walk).
    "anthropic",
    "openai",
    # Backend stack
    "fastapi",
    "uvicorn",
    "starlette",
    "sse_starlette",
    "pydantic",
    "pydantic_core",
    # HTTP + auth + storage
    "httpx",
    "httpcore",
    "h11",
    # h2 is optional HTTP/2 support; only listed if installed locally.
    "anyio",
    "sniffio",
    "dotenv",
    "platformdirs",
    "yaml",
    # Native window
    "webview",
    # Our code
    "api",
    "core",
    "mcp_server",
    # Tool deps
    "mcp",
]

# Anything py2app auto-pulls but we don't actually use. Saves
# ~150 MB combined. Each line is a verified false-positive from a
# dependency walker run.
EXCLUDES = [
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
    "setuptools",  # not needed at runtime; saves ~10 MB
    "pip",
    "wheel",
    "test",
    "tests",
    "docutils",
]

OPTIONS = {
    "argv_emulation": False,  # we don't take CLI args; faster boot
    "packages": PACKAGES,
    # Use `includes` for namespace-package members py2app's old
    # find_module can't enumerate. Modulegraph still walks transitive
    # imports off these.
    "includes": [
        "google.genai",
        "google.auth",
        "google.api_core",
    ],
    "excludes": EXCLUDES,
    "optimize": 2,  # strip docstrings + assertions; trims ~5%
    "plist": {
        "CFBundleName": "FaroAI",
        "CFBundleDisplayName": "FaroAI",
        "CFBundleIdentifier": "com.farolatino.faroai",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.business",
        "NSHighResolutionCapable": True,
        # Don't show the dock icon when launched silently (helps
        # background-launch UX from a future "Login Items" config).
        # Setting to False means a normal foreground app: dock icon
        # + menu bar.
        "LSUIElement": False,
        # Required so the app can talk to localhost without a
        # transport-security exception.
        "NSAppTransportSecurity": {
            "NSAllowsLocalNetworking": True,
        },
        # Human-readable copyright displayed in About.
        "NSHumanReadableCopyright": "© 2026 FaroLatino",
    },
}


setup(
    app=APP,
    name="FaroAI",
    version=VERSION,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app>=0.28"],
)
