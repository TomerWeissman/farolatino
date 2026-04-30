"""Revenue estimation model — MCP tool wrapper.

Converts public Chartmetric data into projected total artist streaming
revenue (across all platforms and all distributors). The core logic
lives in d3_revenue_potential.py; this tool exposes it directly.
"""

from mcp_server.models import build_artist
from mcp_server.server import mcp
from mcp_server.tools.scoring.d3_revenue_potential import estimate_artist_revenue


@mcp.tool()
def estimate_revenue(artist_data: dict) -> dict:
    """Project the artist's TOTAL annual streaming revenue (BRUTO, full catalog).

    Returns the estimated total annual gross streaming royalty across all
    platforms and all distributors — the catalog's market value if a
    single distributor (e.g. FaroLatino) had full rights. Multiply by
    ~0.74 for artist NETO payout, by ~0.26 for distributor cut.

    Uses empirical CPMs from config/cpm_rates.yaml and bucketed
    streams-per-listener multipliers from config/stream_multipliers.yaml,
    both calibrated against FaroLatino's 24-month royalty data.

    Args:
        artist_data: Dict with artist fields matching ArtistProfile model.
    """
    artist = build_artist(artist_data)
    result = estimate_artist_revenue(artist)
    result["scope"] = "total artist BRUTO (all platforms, all distributors)"
    result["payout_split_note"] = (
        "Apply ~0.74 multiplier for artist NETO (typical streaming payout share); "
        "~0.26 for distributor cut. Per-(platform, country) splits in "
        "config/distribution_split.yaml."
    )
    return result
