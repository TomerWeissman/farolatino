"""Run the FaroLatino MCP server: `python -m mcp_server`.

This entrypoint exists specifically to avoid the double-import that
`python -m mcp_server.server` triggers — when server.py is run as
__main__, any `from mcp_server.server import X` inside a tool module
re-imports server.py as `mcp_server.server`, which re-runs all the
tool registrations and creates circular-import errors.

Importing once via this __main__ keeps server.py loaded exactly once.
"""
from mcp_server.server import mcp


if __name__ == "__main__":
    mcp.run()
