"""POST /api/search — disambiguation-friendly artist lookup.

Companion to ``/api/evaluate``: returns up to N Chartmetric candidates
for a query without running the scoring pipeline. The UI uses it for
the "See other matches" panel on Evaluate / Compare and for the
URL-paste fallback when a name returns zero hits.

URL-shaped queries (``https://open.spotify.com/artist/...``,
``https://www.chartmetric.com/artist/...``, ``https://soundcloud.com/...``)
are routed to ``search_artist_by_url`` so a user who pastes a profile
link gets the same disambiguation surface as someone typing a name.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mcp_server.tools.chartmetric_search import search_artist_by_url, search_artists

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=400)
    limit: int = Field(10, ge=1, le=25)


class SearchCandidate(BaseModel):
    cm_id: int | None = None
    name: str | None = None
    code2: str | None = None
    sp_followers: int | None = None
    sp_monthly_listeners: int | None = None
    image_url: str | None = None
    genres: list[str] | None = None
    record_label: str | None = None


class SearchResponse(BaseModel):
    query: str
    count: int
    artists: list[SearchCandidate]
    # If the query was a URL we routed through search_artist_by_url, this
    # carries the platform the URL was recognised as (spotify, youtube…).
    # Plain-name searches leave it as None.
    resolved_from_url: str | None = None
    error: str | None = None


# Anything that smells like a URL — covers Spotify, Chartmetric, YouTube,
# Instagram, TikTok, SoundCloud. Chartmetric's social-search endpoint
# does the heavy lifting once we've identified it as URL-shaped.
_URL_RE = re.compile(r"^\s*(https?://|www\.)", re.IGNORECASE)


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    query = req.query.strip()

    if _URL_RE.match(query):
        # URL path: returns a single candidate (or an error). Wrap it in
        # the same response shape so the UI doesn't need two branches.
        try:
            result = search_artist_by_url(query)
        except Exception as exc:  # noqa: BLE001 — surface any upstream error
            return SearchResponse(
                query=query, count=0, artists=[], error=str(exc)
            )
        if "error" in result:
            return SearchResponse(
                query=query, count=0, artists=[], error=result["error"]
            )
        candidate = SearchCandidate(
            cm_id=result.get("cm_id"),
            name=result.get("name"),
            code2=result.get("code2"),
        )
        return SearchResponse(
            query=query,
            count=1,
            artists=[candidate],
            resolved_from_url=result.get("platform"),
        )

    try:
        result = search_artists(query, limit=req.limit)
    except Exception as exc:  # noqa: BLE001
        return SearchResponse(query=query, count=0, artists=[], error=str(exc))

    artists = [SearchCandidate(**a) for a in (result.get("artists") or [])]
    return SearchResponse(
        query=query,
        count=len(artists),
        artists=artists,
    )
