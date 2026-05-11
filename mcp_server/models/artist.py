"""Unified data models for the FaroLatino A&R pipeline.

ArtistProfile is the central model — Chartmetric tools populate it,
scoring engine consumes it. All fields are Optional so partial data works.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime


@dataclass
class CountryListeners:
    country_code: str  # ISO 3166-1 alpha-2
    listeners: int = 0
    prev_listeners: int = 0


@dataclass
class CityListeners:
    city: str
    country_code: str
    listeners: int = 0
    prev_listeners: int = 0


@dataclass
class Track:
    name: str
    release_date: str = ""  # ISO date string
    isrc: str = ""
    version_type: str = "original"  # original, remix, live, acoustic, etc.
    album_label: str = ""
    spotify_plays: int | None = None
    tiktok_posts: int | None = None
    shazam_count: int | None = None


@dataclass
class Album:
    name: str
    release_date: str = ""
    track_count: int = 0
    album_type: str = ""  # album, single, ep


@dataclass
class PlaylistPlacement:
    playlist_name: str
    platform: str = ""  # spotify, apple_music, deezer, amazon
    is_editorial: bool = False
    followers: int = 0
    position: int | None = None
    added_date: str = ""


@dataclass
class ChartAppearance:
    chart_name: str
    platform: str = ""
    country: str = ""  # ISO alpha-2
    peak_position: int | None = None
    date: str = ""


@dataclass
class Milestone:
    text: str
    date: str = ""
    platform: str = ""
    star_rating: int | None = None


@dataclass
class Insight:
    text: str
    type: str = ""  # acceleration, spike, anomaly, etc.
    date: str = ""
    metric: str = ""
    value: float | None = None


@dataclass
class NeighboringArtist:
    name: str
    cm_id: int | None = None
    career_stage: str = ""
    signed: bool = False
    recent_momentum: str = ""
    country_code: str = ""
    image_url: str = ""
    sp_monthly_listeners: int = 0
    sp_followers: int = 0
    source: str = ""


@dataclass
class ArtistProfile:
    """Unified artist profile assembled from all data sources."""

    # Identity
    cm_id: int = 0
    name: str = ""
    genres: list[str] = field(default_factory=list)
    career_stage: str = ""
    career_trend: str = ""
    career_momentum_score: float = 0.0
    record_label: str | None = None
    distributor: str | None = None
    image_url: str | None = None
    urls: dict[str, str] = field(default_factory=dict)

    # Streaming & social metrics (current + diffs)
    sp_monthly_listeners: int = 0
    sp_monthly_listeners_diff_pct: float | None = None
    sp_followers: int = 0
    sp_followers_diff_pct: float | None = None
    sp_followers_to_listeners_ratio: float | None = None
    sp_popularity: int | None = None
    yt_subscribers: int = 0
    yt_subscribers_diff_pct: float | None = None
    yt_views: int = 0
    yt_daily_views: int | None = None
    tiktok_followers: int = 0
    tiktok_followers_diff_pct: float | None = None
    tiktok_likes: int | None = None
    ig_followers: int = 0
    ig_followers_diff_pct: float | None = None
    shazam_count: int = 0
    shazam_count_diff_pct: float | None = None
    deezer_fans: int = 0
    soundcloud_followers: int = 0
    cpp_score: float = 0.0  # Cross-Platform Performance 0-1

    # Geographic
    listener_countries: list[CountryListeners] = field(default_factory=list)
    listener_cities: list[CityListeners] = field(default_factory=list)
    social_audience_countries: dict[str, list[dict]] = field(default_factory=dict)

    # Catalog
    tracks: list[Track] = field(default_factory=list)
    albums: list[Album] = field(default_factory=list)
    recent_release_count_6m: int = 0
    recent_release_count_12m: int = 0

    # Playlists & charts
    playlists: list[PlaylistPlacement] = field(default_factory=list)
    chart_appearances: list[ChartAppearance] = field(default_factory=list)

    # Signals
    milestones: list[Milestone] = field(default_factory=list)
    noteworthy_insights: list[Insight] = field(default_factory=list)
    neighboring_artists: list[NeighboringArtist] = field(default_factory=list)

    # Engagement
    ig_engagement_rate: float | None = None

    # Native Spotify enrichment (v0.5.0 — backward-compatible, optional)
    sp_artist_id: str | None = None
    sp_top_tracks: list[dict] = field(default_factory=list)
    sp_audio_features: dict = field(default_factory=dict)

    # Native YouTube enrichment (v0.5.0)
    yt_latest_videos: list[dict] = field(default_factory=list)

    # Metadata
    data_fetched_at: str = ""  # ISO datetime
    data_completeness: float = 0.0  # 0-1, how many fields are populated

    @property
    def editorial_playlists(self) -> list[PlaylistPlacement]:
        return [p for p in self.playlists if p.is_editorial]

    def compute_data_completeness(self) -> float:
        """Calculate what fraction of key scoring fields have data."""
        key_fields = [
            self.sp_monthly_listeners > 0,
            self.sp_monthly_listeners_diff_pct is not None,
            self.sp_followers > 0,
            self.career_stage != "",
            self.career_trend != "",
            self.career_momentum_score > 0,
            len(self.listener_countries) > 0,
            len(self.tracks) > 0,
            self.cpp_score > 0,
            self.yt_subscribers > 0,
            self.tiktok_followers > 0,
            self.ig_followers > 0,
            self.shazam_count > 0,
        ]
        self.data_completeness = sum(key_fields) / len(key_fields)
        return self.data_completeness


@dataclass
class DimensionResult:
    """Score output from a single dimension scorer."""
    score: float  # 0-100
    confidence: float  # 0-1 (how complete was the input data)
    rationale: str  # one-line explanation for the dossier


def _from_dict(cls, item: dict):
    """Construct a dataclass instance from a dict, ignoring keys that aren't
    fields of the dataclass. Without this, any extra key from the upstream
    Chartmetric payload (or a model-rewritten payload) would raise
    `TypeError: <Cls>.__init__() got an unexpected keyword argument`.
    """
    valid = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in item.items() if k in valid})


def build_artist(data: dict) -> ArtistProfile:
    """Build an ArtistProfile from a dict, handling nested dataclass fields."""
    nested_mappings = {
        "listener_countries": CountryListeners,
        "listener_cities": CityListeners,
        "tracks": Track,
        "albums": Album,
        "playlists": PlaylistPlacement,
        "chart_appearances": ChartAppearance,
        "milestones": Milestone,
        "noteworthy_insights": Insight,
        "neighboring_artists": NeighboringArtist,
    }

    valid_top = {f.name for f in fields(ArtistProfile)}
    processed = {}
    for key, value in data.items():
        if key not in valid_top:
            continue  # silently drop unknown top-level keys (forward-compat)
        if key in nested_mappings and isinstance(value, list):
            cls = nested_mappings[key]
            processed[key] = [_from_dict(cls, item) if isinstance(item, dict) else item for item in value]
        else:
            processed[key] = value

    return ArtistProfile(**processed)
