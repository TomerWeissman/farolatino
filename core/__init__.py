"""Pure-Python helpers used by the FastAPI app (api/).

Lives in core/ rather than api/ because nothing here depends on FastAPI
(or any web framework) — they're plain subprocess + file-I/O helpers
that can be exercised in headless tests or scripts without spinning up
a server.
"""
