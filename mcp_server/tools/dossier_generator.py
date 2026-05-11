"""Dossier generator — assembles a structured artist dossier from scored data."""

from core.cadence import compute_release_cadence
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
    album_release_dates = [a.release_date for a in artist.albums if a.release_date]
    sp_cadence = compute_release_cadence(album_release_dates)
    top_tracks = [
        {
            "name": tr.get("name") or "",
            "release_date": tr.get("release_date") or "",
            "popularity": tr.get("popularity"),
            "spotify_id": tr.get("id"),
        }
        for tr in (artist.sp_top_tracks or [])
    ]
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
        "latest_release_date": sp_cadence.get("latest_date"),
        "days_since_latest_release": sp_cadence.get("days_since_latest"),
        # Prefer the 6m window when present, else fall back to 12m so
        # legacy/heritage acts with sparse recent activity still report
        # a number; tag downstream with `_window` so the UI can label it.
        "release_cadence_days": sp_cadence.get("cadence_days_6m") or sp_cadence.get("cadence_days_12m"),
        "cadence_trend": sp_cadence.get("trend"),
        "top_tracks": top_tracks,
    }

    # 7b. Sound profile (Spotify audio-features average across top tracks)
    avg = artist.sp_audio_features or {}
    sound_profile = {
        "danceability": avg.get("danceability"),
        "energy": avg.get("energy"),
        "tempo": avg.get("tempo"),
        "sample_size": avg.get("sample_size") or len(top_tracks),
    } if avg else None

    # 7c. Content velocity (Spotify + YouTube cadence + recent video performance)
    yt_videos = artist.yt_latest_videos or []
    yt_top = artist.yt_top_videos or []
    yt_publish_dates = [v.get("published_at") for v in yt_videos if v.get("published_at")]
    yt_cadence = compute_release_cadence([d[:10] for d in yt_publish_dates if d])
    yt_views = [v.get("view_count") for v in yt_videos if v.get("view_count")]
    yt_ratios = [v.get("like_ratio") for v in yt_videos if v.get("like_ratio") is not None]
    # Comments-per-view (v0.5.2) — sharper engagement signal than like
    # ratio because comments require effort. Bot-bought views rarely
    # come with scripted comments; real fans leave them.
    yt_cpv_vals = [
        (v.get("comment_count") / v["view_count"] * 100)
        for v in yt_videos
        if v.get("view_count") and v.get("comment_count") is not None
    ]
    yt_block: dict = {
        "latest_date": yt_cadence.get("latest_date"),
        "days_since_latest": yt_cadence.get("days_since_latest"),
        "cadence_days": yt_cadence.get("cadence_days_6m") or yt_cadence.get("cadence_days_12m"),
        "trend": yt_cadence.get("trend"),
        "avg_views_recent_3": (sum(yt_views) // len(yt_views)) if yt_views else None,
        "avg_like_ratio_pct": (sum(yt_ratios) / len(yt_ratios)) if yt_ratios else None,
        "avg_comments_per_view_pct": (sum(yt_cpv_vals) / len(yt_cpv_vals)) if yt_cpv_vals else None,
        "latest_videos": [
            {
                "title": v.get("title") or "",
                "published_at": v.get("published_at") or "",
                "view_count": v.get("view_count") or 0,
                "like_count": v.get("like_count") or 0,
            }
            for v in yt_videos
        ],
        "top_videos": [
            {
                "id": v.get("id") or "",
                "title": v.get("title") or "",
                "published_at": v.get("published_at") or "",
                "view_count": v.get("view_count") or 0,
                "like_count": v.get("like_count") or 0,
                "comment_count": v.get("comment_count") or 0,
                "like_ratio": v.get("like_ratio"),
                "thumbnail_url": v.get("thumbnail_url"),
                "url": f"https://www.youtube.com/watch?v={v['id']}" if v.get("id") else None,
            }
            for v in yt_top
        ],
    }
    content_velocity = {
        "spotify": {
            "latest_date": sp_cadence.get("latest_date"),
            "days_since_latest": sp_cadence.get("days_since_latest"),
            "cadence_days": sp_cadence.get("cadence_days_6m") or sp_cadence.get("cadence_days_12m"),
            "trend": sp_cadence.get("trend"),
        },
        "youtube": yt_block if yt_videos else None,
    }

    # 8. Risk signals
    dims = score_result.get("dimensions", {})
    risk = {
        "engagement_quality": dims.get("engagement_quality", {}).get("rationale", "N/A"),
        "platform_concentration": dims.get("platform_diversification", {}).get("rationale", "N/A"),
        "content_velocity": dims.get("content_velocity", {}).get("rationale", "N/A"),
    }

    # 9. Competitive context
    # Includes image_url + country_code + sp_monthly_listeners so the
    # dashboard's Similar-artists section can render a profile photo
    # next to the name. The chat-side Markdown renderer also uses these
    # for its summary line.
    competitive = {
        "similar_artists": [
            {
                "name": n.name,
                "image_url": n.image_url or None,
                "country_code": n.country_code or None,
                "sp_monthly_listeners": n.sp_monthly_listeners or None,
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

    result = {
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
        "content_velocity": content_velocity,
    }
    if sound_profile:
        result["sound_profile"] = sound_profile
    return result
