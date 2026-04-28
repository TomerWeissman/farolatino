"""Dossier generator — assembles a structured artist dossier from scored data."""

from mcp_server.models import build_artist
from mcp_server.server import mcp


def _pct_change(current: int, previous: int) -> str:
    if previous == 0:
        return "N/A"
    change = ((current - previous) / previous) * 100
    return f"{change:+.1f}%"


@mcp.tool()
def generate_dossier(artist_data: dict, score_result: dict, revenue_result: dict | None = None) -> dict:
    """Assemble a complete artist dossier from scored data.

    Args:
        artist_data: Dict with artist fields matching ArtistProfile model.
        score_result: Output from compute_prospect_score.
        revenue_result: Optional output from estimate_revenue.
    """
    artist = build_artist(artist_data)

    # 1. Identity
    identity = {
        "name": artist.name,
        "genres": artist.genres,
        "career_stage": artist.career_stage,
        "career_trend": artist.career_trend,
        "label": artist.record_label,
        "distributor": artist.distributor,
        "image": artist.image_url,
        "urls": artist.urls,
    }

    # 2. Metrics overview
    metrics = {
        "spotify": {
            "monthly_listeners": artist.sp_monthly_listeners,
            "monthly_listeners_change": f"{artist.sp_monthly_listeners_diff_pct:+.1f}%" if artist.sp_monthly_listeners_diff_pct is not None else "N/A",
            "followers": artist.sp_followers,
            "popularity": artist.sp_popularity,
        },
        "youtube": {
            "subscribers": artist.yt_subscribers,
            "views": artist.yt_views,
        },
        "tiktok": {
            "followers": artist.tiktok_followers,
            "likes": artist.tiktok_likes,
        },
        "instagram": {
            "followers": artist.ig_followers,
            "engagement_rate": f"{artist.ig_engagement_rate:.1f}%" if artist.ig_engagement_rate is not None else "N/A",
        },
        "other": {
            "shazam_count": artist.shazam_count,
            "deezer_fans": artist.deezer_fans,
            "soundcloud_followers": artist.soundcloud_followers,
        },
        "cpp_score": artist.cpp_score,
    }

    # 3. Prospect score breakdown
    prospect_score = {
        "overall": score_result.get("prospect_score", 0),
        "tier": score_result.get("tier", "PASS"),
        "confidence": score_result.get("confidence", 0),
        "data_completeness": score_result.get("data_completeness", 0),
        "profile_used": score_result.get("profile_used", "default"),
        "dimensions": score_result.get("dimensions", {}),
    }

    # 4. Geographic profile
    top_markets = sorted(artist.listener_countries, key=lambda c: c.listeners, reverse=True)[:5]
    geographic = {
        "top_markets": [
            {
                "country": m.country_code,
                "listeners": m.listeners,
                "growth": _pct_change(m.listeners, m.prev_listeners),
            }
            for m in top_markets
        ],
    }

    # 5. Revenue projection
    revenue = revenue_result if revenue_result else {"note": "Revenue model not run"}

    # 6. Career trajectory
    career = {
        "stage": artist.career_stage,
        "trend": artist.career_trend,
        "momentum_score": artist.career_momentum_score,
        "milestones": [
            {"text": m.text, "date": m.date, "platform": m.platform}
            for m in artist.milestones[:5]
        ],
    }

    # 7. Catalog & activity
    recent_tracks = sorted(artist.tracks, key=lambda t: t.release_date, reverse=True)[:5]
    catalog = {
        "releases_6m": artist.recent_release_count_6m,
        "releases_12m": artist.recent_release_count_12m,
        "total_tracks": len(artist.tracks),
        "latest_tracks": [
            {"name": t.name, "release_date": t.release_date, "isrc": t.isrc}
            for t in recent_tracks
        ],
        "editorial_playlists": len(artist.editorial_playlists),
        "total_playlists": len(artist.playlists),
    }

    # 8. Risk signals
    dims = score_result.get("dimensions", {})
    risk = {
        "engagement_quality": dims.get("engagement_quality", {}).get("rationale", "N/A"),
        "platform_concentration": dims.get("platform_diversification", {}).get("rationale", "N/A"),
        "content_velocity": dims.get("content_velocity", {}).get("rationale", "N/A"),
    }

    # 9. Competitive context
    competitive = {
        "similar_artists": [
            {
                "name": n.name,
                "career_stage": n.career_stage,
                "signed": n.signed,
                "momentum": n.recent_momentum,
            }
            for n in artist.neighboring_artists[:5]
        ],
    }

    # 10. Actionable info
    actionable = {
        "social_links": artist.urls,
        "tier": score_result.get("tier", "PASS"),
    }

    return {
        "identity": identity,
        "metrics": metrics,
        "prospect_score": prospect_score,
        "geographic_profile": geographic,
        "revenue_projection": revenue,
        "career_trajectory": career,
        "catalog": catalog,
        "risk_signals": risk,
        "competitive_context": competitive,
        "actionable": actionable,
    }
