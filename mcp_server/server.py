"""FaroLatino A&R Pipeline — MCP Server

Registers all tools for the artist scouting and scoring pipeline.
Run with: fastmcp run mcp_server/server.py
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

if __name__ == "__main__":
    mcp.run()
