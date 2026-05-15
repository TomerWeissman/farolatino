"""Shared country-cluster filter for "similar artists" lists.

Lifted out of composite_similar.py in v0.5.3 so the dossier_generator
(which feeds the Evaluate page's "Similar Artists" section) can apply
the same filtering. Before, the chat-side `@similar` skill went through
composite_similar and got tidy Latin-market neighbors, while the
Evaluate page's similar-artists list rendered Chartmetric's raw
audience-overlap clustering — frequently a Bad Bunny seed surfaced
Justin Bieber, Brent Rivera, etc. as "similar". Same data; different
filtering. Both surfaces now share this module.

Why no genre filter (yet):
    The neighboring-artists endpoint returns minimal fields per peer —
    name, country, image, follower counts — no genre array. Adding
    genre overlap would require either an extra API call per neighbor
    (15 calls per evaluate, hits the 1.05 req/s Chartmetric ceiling
    hard) or schema changes to cache full peer profiles. Country
    filtering catches the worst of the cross-genre noise without
    paying that cost; revisit once we have per-neighbor genres in the
    cache.
"""
from __future__ import annotations


# Countries whose music markets are part of the Latin scene FaroLatino
# scouts in. When the seed is one of these, we filter neighbors to this
# whole set rather than just exact-country match — most "neighbors" of a
# PR superstar like Bad Bunny are global US/CA pop stars (audience
# overlap, not genre), so an exact-PR filter would leave basically only
# the seed itself in the list. The cluster catches Karol G (CO) for a
# Bad Bunny (PR) seed, etc.
LATIN_MARKETS: frozenset[str] = frozenset({
    "PR", "MX", "CO", "AR", "ES", "VE", "DO", "CL", "EC", "PE",
    "UY", "PY", "BO", "CU", "GT", "HN", "NI", "CR", "PA", "SV", "BR",
})


def country_filter_set(seed_country: str | None) -> frozenset[str] | None:
    """Return the country set we'll filter neighbors against, or None to
    skip filtering. Latin seeds use the full Latin-market cluster;
    non-Latin seeds use an exact country match (safer default — we
    don't have other regional clusters defined). Empty/missing
    country → no filter."""
    if not seed_country:
        return None
    cc = seed_country.upper()
    if cc in LATIN_MARKETS:
        return LATIN_MARKETS
    return frozenset({cc})


def filter_neighbors_by_country(
    seed_country: str | None,
    neighbors: list,
    country_getter=lambda n: (
        # Default getter handles both dict (raw Chartmetric payload)
        # and dataclass (ArtistProfile.neighboring_artists)
        getattr(n, "country_code", None) if hasattr(n, "country_code") else n.get("country_code")
    ),
) -> tuple[list, bool]:
    """Drop neighbors outside the seed's country cluster.

    Returns ``(filtered_list, was_applied)``. ``was_applied`` is True
    iff filtering ran and left at least one neighbor — i.e. callers
    that fall back to the unfiltered list when the filter empties out
    can render a "showed unfiltered set" hint to the user.

    The getter callback lets both raw dicts and dataclasses share this
    helper without each module having to convert shapes first.
    """
    countries = country_filter_set(seed_country)
    if countries is None:
        return neighbors, False
    filtered = [
        n for n in neighbors
        if (country_getter(n) or "").upper() in countries
    ]
    if not filtered:
        # Better to show noisy results than an empty section.
        return neighbors, False
    return filtered, True
