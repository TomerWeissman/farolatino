"""FastAPI backend for the FaroLatino A&R dashboard.

Wraps the existing pure-Python `core/` helpers (claude_runner, run_log,
skill_registry) and the MCP server. Serves the Next.js static build
from `web/out/` so a single uvicorn process delivers both API and UI.
"""
