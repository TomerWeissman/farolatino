"""Pure-Python helpers used by the FastAPI app (api/).

Lives in core/ rather than api/ because nothing here depends on FastAPI
(or any web framework) — they're plain subprocess + file-I/O helpers
that can be exercised in headless tests or scripts without spinning up
a server.
"""

# Single source of truth for the app version. Read by:
#   - packaging/setup_py2app.py — sets CFBundleVersion + CFBundleShortVersionString
#   - core/updater.py — compares against GitHub Releases tags
#   - api/routes/updates.py — returned to the UI's "Check for updates"
__version__ = "0.2.1"
