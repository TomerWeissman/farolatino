"""FaroLatino A&R Pipeline — tool registry.

V2: tools run in-process. The ``@mcp.tool()`` decorator is preserved as
inert metadata for two reasons: (1) FastMCP's ``mcp.run()`` is never
called from V2, so the decorator is a no-op for the live app; (2) the
modules can still be loaded as a real MCP server (``python -m mcp_server``)
for any future remote-MCP integration without changing tool source.

Tool dispatch in V2 happens via direct Python imports — see
``core/llm/tool_dispatch.py``. The 21 tool functions registered here
are exactly what the agent runner calls.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("farolatino-ar-pipeline")

# Import tool modules — each registers its tools against the shared `mcp` instance
from mcp_server.tools import config_manager  # noqa: E402, F401
from mcp_server.tools import data_cache  # noqa: E402, F401
from mcp_server.tools import alert_router  # noqa: E402, F401
from mcp_server.tools import revenue_model  # noqa: E402, F401
from mcp_server.tools import dossier_generator  # noqa: E402, F401
from mcp_server.tools.scoring import engine  # noqa: E402, F401

# Chartmetric API tools (require CHARTMETRIC_REFRESH_TOKEN in .env)
from mcp_server.tools import chartmetric_search  # noqa: E402, F401
from mcp_server.tools import chartmetric_artist  # noqa: E402, F401
from mcp_server.tools import chartmetric_discovery  # noqa: E402, F401

# Composite tools — chain multiple primitive tools server-side so the model
# makes only one MCP call per skill (vs. 6+ in the unfactored flow).
from mcp_server.tools import composite_evaluate  # noqa: E402, F401
from mcp_server.tools import composite_similar  # noqa: E402, F401

# Spotify + YouTube — direct API integrations for cross-validation against
# Chartmetric's daily snapshot. Both auto-handle auth via .env credentials.
from mcp_server.tools import spotify_search  # noqa: E402, F401
from mcp_server.tools import youtube_search  # noqa: E402, F401

if __name__ == "__main__":
    mcp.run()
