"""GET /api/onboarding/status — does the user still need to set up their keys?

Two states the UI cares about:

- ``needs_onboarding`` — the LLM key is missing. Without it, chat
  literally can't work; the frontend redirects ``/`` to ``/onboarding``
  in this state on first launch.
- ``has_chartmetric`` — chat works without it (free-form prose), but
  the @evaluate / @similar skills can't fetch real data. Shows as a
  softer "set up Chartmetric for full features" hint, not a redirect.

Spotify + YouTube are optional enrichment data sources; missing them
doesn't degrade the core flow noticeably.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from core.llm import detect_provider_name

router = APIRouter()


class OnboardingStatus(BaseModel):
    needs_onboarding: bool       # blocking — no LLM key, can't chat at all
    has_llm_key: bool            # true when LLM_API_KEY (or legacy) is set
    has_chartmetric: bool        # true when CHARTMETRIC_REFRESH_TOKEN is set
    has_spotify: bool            # optional enrichment
    has_youtube: bool            # optional enrichment
    detected_provider: str       # "anthropic" | "openai" | "gemini" | "none"


@router.get("/onboarding/status", response_model=OnboardingStatus)
def get_onboarding_status() -> OnboardingStatus:
    has_llm = detect_provider_name() != "none"
    has_chart = bool(os.getenv("CHARTMETRIC_REFRESH_TOKEN"))
    has_spot = bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))
    has_yt = bool(
        os.getenv("YOUTUBE_API_KEY")
        or all(
            os.getenv(k)
            for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
        )
    )

    return OnboardingStatus(
        needs_onboarding=not has_llm,
        has_llm_key=has_llm,
        has_chartmetric=has_chart,
        has_spotify=has_spot,
        has_youtube=has_yt,
        detected_provider=detect_provider_name(),
    )
