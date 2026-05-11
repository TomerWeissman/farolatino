"""Bot-stream / fake-engagement detection — composite heuristic.

D6 (engagement_quality) already computes most of these signals and bakes
them into a 0-100 score. That blend reads as "one factor among seven"
when surfaced in the Scoring section. This module hoists the same
signals into a discrete **risk row** so an A&R analyst sees ⚠️ at a
glance instead of having to parse a dimension rationale.

The thresholds intentionally mirror ``d6_engagement_quality.py`` so we
don't have two sources of truth — change the underlying signal once,
both surfaces update.

Composite logic: at least **2 signals must fire** for ``level="high"``;
1 signal → ``"medium"``; 0 signals → ``"low"`` (no risk row rendered).
"""
from __future__ import annotations

from mcp_server.models import ArtistProfile


def assess_bot_risk(artist: ArtistProfile, yt_videos: list[dict] | None = None) -> dict:
    """Return a bot-risk assessment for an artist.

    Args:
        artist: Populated ``ArtistProfile``.
        yt_videos: Latest YouTube videos with ``view_count`` / ``like_ratio``
            / ``comment_count``. Pass ``artist.yt_latest_videos`` from the
            caller (typed loosely because the dossier path uses plain dicts).

    Returns a dict::

        {
          "level": "low" | "medium" | "high",
          "score": int,                    # 0-100, 100 = clean
          "reasons": list[str],            # one short line per firing signal
        }
    """
    reasons: list[str] = []
    yt_videos = yt_videos or []

    # Signal 1: Spotify follower/listener ratio — < 0.05 with > 10K
    # monthly listeners is the bot-streams signature D6 already calls out.
    ratio = artist.sp_followers_to_listeners_ratio
    if (
        ratio is not None
        and ratio < 0.05
        and artist.sp_monthly_listeners > 10_000
    ):
        reasons.append(
            f"Spotify follower-to-listener ratio {ratio:.2f} on "
            f"{artist.sp_monthly_listeners:,} monthly listeners "
            f"— typical bot-streams signature"
        )

    # Signal 2: Growth divergence — listeners spiking faster than
    # followers means streams without real audience growth.
    sp_l_diff = artist.sp_monthly_listeners_diff_pct
    sp_f_diff = artist.sp_followers_diff_pct
    if (
        sp_l_diff is not None
        and sp_f_diff is not None
        and sp_l_diff > 200
        and sp_f_diff < 20
    ):
        reasons.append(
            f"Monthly listeners +{sp_l_diff:.0f}% but followers only "
            f"+{sp_f_diff:.0f}% — stream surge without audience growth"
        )

    # Signal 3: YouTube like ratio — organic music videos typically run
    # 1-8% likes/views; sub-0.3% on > 100K views suggests bought views.
    for v in yt_videos:
        views = v.get("view_count") or 0
        lr = v.get("like_ratio")
        if views > 100_000 and lr is not None and lr < 0.3:
            reasons.append(
                f"YouTube video '{(v.get('title') or '—')[:40]}' has "
                f"{lr:.2f}% like ratio on {views:,} views (organic music "
                f"runs 1-8%)"
            )
            break  # one example is enough; don't pile on

    # Signal 4: YouTube comments-per-view — < 0.005% on > 100K views.
    # Comments require effort; bot view-farms rarely script comments.
    for v in yt_videos:
        views = v.get("view_count") or 0
        comments = v.get("comment_count") or 0
        if views > 100_000:
            cpv = comments / views * 100
            if cpv < 0.005:
                reasons.append(
                    f"YouTube video '{(v.get('title') or '—')[:40]}' has "
                    f"{cpv:.3f}% comments-per-view on {views:,} views — "
                    f"comments require effort, bots rarely script them"
                )
                break

    # Signal 5: Cross-platform mismatch — a real artist with > 500K
    # Spotify monthly listeners has parallel YouTube + TikTok presence.
    if (
        artist.sp_monthly_listeners > 500_000
        and artist.yt_subscribers < 10_000
        and artist.tiktok_followers < 50_000
    ):
        reasons.append(
            f"{artist.sp_monthly_listeners:,} Spotify listeners but only "
            f"{artist.yt_subscribers:,} YouTube subs + {artist.tiktok_followers:,} "
            f"TikTok followers — real artists at this Spotify tier have "
            f"substantial parallel presence"
        )

    # Composite level — ≥2 signals = high, 1 = medium, 0 = low (no
    # risk row rendered).
    if len(reasons) >= 2:
        level = "high"
    elif len(reasons) == 1:
        level = "medium"
    else:
        level = "low"

    # Score: 100 = clean, each firing signal subtracts 25 points. Capped
    # at 0 to avoid negatives when an artist trips multiple signals.
    score = max(0, 100 - 25 * len(reasons))

    return {"level": level, "score": score, "reasons": reasons}
