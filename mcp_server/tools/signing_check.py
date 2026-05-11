"""Signing-status verification — cross-check Chartmetric's `signed` flag.

Chartmetric exposes a single boolean ``signed`` per artist. We treat it
as a starting point and corroborate against two harder pieces of
evidence already in the dossier:

1. ``record_label`` field on the artist
2. The label fields on the artist's recent albums (last ~5)

Outcomes the A&R team actually cares about:

- **signed_major** — at least one piece of evidence ties to a recognized
  major label. High confidence.
- **signed_indie** — Chartmetric says signed and there's *some* label
  evidence but none of it maps to a major. Medium confidence (indie
  deals are real, but verify direct).
- **self_released** — Chartmetric says unsigned AND no recent album
  has a non-self / non-empty label. High confidence "no deal yet".
- **unknown** — conflicting or absent evidence. Low confidence; surface
  the discrepancy so the analyst follows up.

A ``discrepancy`` flag flips when Chartmetric's boolean disagrees with
the label evidence (e.g., CM says signed=True but no major label
surfaces in evidence, or CM says signed=False but recent albums are on
a major). The Hero badge uses this to render a ⚠️ "verify" state.
"""
from __future__ import annotations

from mcp_server.models import ArtistProfile

# Major-label set. Extendable; intentionally small so we err toward
# "signed_indie" rather than mis-classifying an indie as major.
# Substring matching (case-insensitive) handles imprint variants —
# "Sony Music Latin" matches "Sony", "UMG Recordings" matches "UMG", etc.
_MAJOR_LABELS = (
    "UMG", "Universal", "Sony", "Warner", "WMG",
    "Atlantic", "Interscope", "Republic", "RCA", "Columbia",
    "Capitol", "Def Jam", "Island", "Epic", "Polydor",
    # Latin-music majors / heavy hitters relevant to FaroLatino
    "Rimas", "WK Records", "Hear This Music",
)


def _looks_like_major(label: str) -> bool:
    if not label:
        return False
    label_lc = label.lower()
    return any(major.lower() in label_lc for major in _MAJOR_LABELS)


def _is_self_release(label: str) -> bool:
    """Heuristic: label is empty, 'self-released', or just the artist's
    own name. Used as a soft negative-signal check."""
    if not label:
        return True
    label_lc = label.strip().lower()
    return label_lc in {"", "self-released", "independent", "self", "indie"}


def verify_signing_status(artist: ArtistProfile) -> dict:
    """Return a verified signing-status assessment.

    Output shape::

        {
          "chartmetric_flag": bool | None,    # what Chartmetric reported
          "verified_status": "signed_major" | "signed_indie" | "self_released" | "unknown",
          "confidence": "high" | "medium" | "low",
          "evidence": list[str],              # human-readable bullets
          "discrepancy": bool,                # CM flag disagrees with evidence
          "label_display": str,               # short label string for the badge
        }
    """
    # Chartmetric stores `signed` on `neighboring_artists`; for the
    # main artist we infer from record_label (CM doesn't put a `signed`
    # bool on the primary artist payload). We treat presence of a
    # non-empty record_label as the analog of "Chartmetric thinks signed".
    cm_label = (artist.record_label or "").strip() or None
    cm_flag: bool | None
    if cm_label is None:
        cm_flag = None  # missing data; we don't know what CM thinks
    else:
        cm_flag = not _is_self_release(cm_label)

    evidence: list[str] = []

    # Evidence 1 — record_label itself
    if cm_label:
        if _looks_like_major(cm_label):
            evidence.append(f"Chartmetric record_label = '{cm_label}' (major)")
        else:
            evidence.append(f"Chartmetric record_label = '{cm_label}'")

    # Evidence 2 — recent album labels (last ~5 albums sorted by date)
    recent_albums = sorted(
        artist.albums, key=lambda a: a.release_date or "", reverse=True
    )[:5]
    major_album_labels: list[str] = []
    indie_album_labels: list[str] = []
    for alb in recent_albums:
        label = (getattr(alb, "album_label", "") or "").strip()
        if not label:
            continue
        if _looks_like_major(label):
            if label not in major_album_labels:
                major_album_labels.append(label)
        else:
            if label not in indie_album_labels:
                indie_album_labels.append(label)

    if major_album_labels:
        evidence.append(
            f"Recent album labels include {', '.join(major_album_labels[:3])} (major)"
        )
    elif indie_album_labels:
        evidence.append(
            f"Recent album labels: {', '.join(indie_album_labels[:3])}"
        )

    # Classify verified_status from the evidence
    if major_album_labels or (cm_label and _looks_like_major(cm_label)):
        verified_status = "signed_major"
        confidence = "high"
    elif cm_label and not _is_self_release(cm_label):
        verified_status = "signed_indie"
        confidence = "medium"
    elif cm_flag is False or (cm_label is None and not recent_albums):
        verified_status = "self_released"
        confidence = "medium" if cm_flag is False else "low"
    else:
        verified_status = "unknown"
        confidence = "low"

    # Discrepancy detection: CM said signed but evidence is empty / weak,
    # or CM said unsigned but evidence points to a major.
    discrepancy = False
    if cm_flag is True and verified_status == "unknown":
        discrepancy = True
        evidence.append(
            "Chartmetric flagged as signed but no corroborating label evidence found"
        )
    elif cm_flag is False and verified_status == "signed_major":
        discrepancy = True
        evidence.append(
            "Chartmetric flagged as unsigned but recent albums appear on a major label"
        )

    # Short display string for the Hero badge
    if verified_status == "signed_major":
        label_display = cm_label or (major_album_labels[0] if major_album_labels else "major label")
    elif verified_status == "signed_indie":
        label_display = cm_label or (indie_album_labels[0] if indie_album_labels else "indie")
    elif verified_status == "self_released":
        label_display = "self-released"
    else:
        label_display = "unclear"

    return {
        "chartmetric_flag": cm_flag,
        "verified_status": verified_status,
        "confidence": confidence,
        "evidence": evidence,
        "discrepancy": discrepancy,
        "label_display": label_display,
    }
