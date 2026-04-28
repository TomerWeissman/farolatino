"""Revenue estimation model — MCP tool wrapper.

Converts public streaming data into projected earnings using
FaroLatino's CPM rates by country and platform. The core logic
lives in d3_revenue_potential.py; this tool exposes it directly.
"""

from mcp_server.models import build_artist
from mcp_server.server import mcp
from mcp_server.tools.scoring.d3_revenue_potential import estimate_artist_revenue


@mcp.tool()
def estimate_revenue(artist_data: dict) -> dict:
    """Project 12-month revenue from an artist's streaming metrics and geographic distribution.

    Uses CPM rates from config/cpm_rates.yaml and the artist's listener
    geography to estimate revenue per platform. Growth trajectory from
    career momentum adjusts the annual projection.

    Args:
        artist_data: Dict with artist fields matching ArtistProfile model.
    """
    artist = build_artist(artist_data)
    result = estimate_artist_revenue(artist)
    result["note"] = "Uses placeholder CPMs — recalibrate with FaroLatino actuals"
    return result
