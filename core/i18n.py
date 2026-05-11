"""Backend translation tables for user-visible strings.

Used by the dossier renderer + composite skills + a couple of error
hints that travel from FastAPI back to the UI's structured-error
banner. Keys are dot-notated by surface (``dossier.section.reach``,
``dossier.label.annual_gross_bruto``) so the same key works on both
the frontend (``web/lib/i18n/messages.ts``) and the backend.

Intentionally a flat dict, not gettext / Babel — volume is ~120
strings, deps stay unchanged, no plural forms needed.
"""
from __future__ import annotations

from typing import Literal

from core.preferences import DEFAULT_LANGUAGE

Language = Literal["en", "es"]


# Each key maps to a {lang: string} dict. Missing translations fall
# back to English so a half-translated PR still renders cleanly.
_MESSAGES: dict[str, dict[str, str]] = {
    # ─── Section headers ─────────────────────────────────────────────
    "dossier.section.revenue": {
        "en": "Total Artist Revenue Projection",
        "es": "Proyección de ingresos totales del artista",
    },
    "dossier.section.reach": {"en": "Reach", "es": "Alcance"},
    "dossier.section.scoring": {"en": "Scoring", "es": "Puntuación"},
    "dossier.section.top_markets": {"en": "Top markets", "es": "Mercados principales"},
    "dossier.section.catalog": {"en": "Catalog", "es": "Catálogo"},
    "dossier.section.similar": {"en": "Similar artists", "es": "Artistas similares"},
    "dossier.section.similar_tier": {
        "en": "Similar artists (tier-similar)",
        "es": "Artistas similares (mismo nivel)",
    },
    "dossier.section.risks": {"en": "Risk signals", "es": "Señales de riesgo"},
    "dossier.section.recommendation": {"en": "Recommendation", "es": "Recomendación"},
    "dossier.section.action": {"en": "Action", "es": "Acción"},
    "dossier.section.geographic_profile": {
        "en": "Geographic Profile",
        "es": "Perfil geográfico",
    },
    "dossier.section.dimension_breakdown": {
        "en": "Dimension Breakdown",
        "es": "Desglose por dimensión",
    },
    "dossier.section.similar_legacy": {
        "en": "Similar Artists",
        "es": "Artistas similares",
    },
    "dossier.section.risks_legacy": {
        "en": "Risk Signals",
        "es": "Señales de riesgo",
    },

    # ─── Confidence levels (revenue projection) ──────────────────────
    "dossier.confidence.high": {"en": "High", "es": "Alta"},
    "dossier.confidence.medium": {"en": "Medium", "es": "Media"},
    "dossier.confidence.low": {"en": "Low", "es": "Baja"},

    # ─── Confidence reasons ──────────────────────────────────────────
    "dossier.confidence.reason.low_listeners": {
        "en": "Spotify monthly listeners < 50K",
        "es": "oyentes mensuales de Spotify < 50K",
    },
    "dossier.confidence.reason.low_followers": {
        "en": "Spotify followers < 10K",
        "es": "seguidores de Spotify < 10K",
    },
    "dossier.confidence.reason.no_yt": {
        "en": "Chartmetric reports 0 YouTube subscribers",
        "es": "Chartmetric reporta 0 suscriptores de YouTube",
    },
    "dossier.confidence.reason.strong_coverage": {
        "en": "active artist with strong Chartmetric coverage",
        "es": "artista activo con buena cobertura de Chartmetric",
    },
    "dossier.confidence.reason.moderate_coverage": {
        "en": "moderate Chartmetric coverage",
        "es": "cobertura moderada de Chartmetric",
    },

    # ─── Table column titles ─────────────────────────────────────────
    "dossier.col.metric": {"en": "Metric", "es": "Métrica"},
    "dossier.col.estimate": {"en": "Estimate", "es": "Estimado"},
    "dossier.col.range": {"en": "Range", "es": "Rango"},
    "dossier.col.platform": {"en": "Platform", "es": "Plataforma"},
    "dossier.col.audience": {"en": "Audience", "es": "Audiencia"},
    "dossier.col.detail": {"en": "Detail", "es": "Detalle"},
    "dossier.col.dimension": {"en": "Dimension", "es": "Dimensión"},
    "dossier.col.score": {"en": "Score", "es": "Puntaje"},
    "dossier.col.why": {"en": "Why", "es": "Razón"},
    "dossier.col.country": {"en": "Country", "es": "País"},
    "dossier.col.listeners": {"en": "Listeners", "es": "Oyentes"},
    "dossier.col.growth": {"en": "Growth", "es": "Crecimiento"},
    "dossier.col.artist": {"en": "Artist", "es": "Artista"},
    "dossier.col.tier": {"en": "Tier", "es": "Nivel"},
    "dossier.col.monthly_listeners": {
        "en": "Monthly listeners",
        "es": "Oyentes mensuales",
    },
    "dossier.col.signed": {"en": "Signed", "es": "Firmado"},
    "dossier.col.weight": {"en": "Weight", "es": "Peso"},
    "dossier.col.contribution": {"en": "Contribution", "es": "Contribución"},
    "dossier.col.confidence": {"en": "Confidence", "es": "Confianza"},

    # ─── Revenue table rows ──────────────────────────────────────────
    "dossier.revenue.annual_gross": {
        "en": "**Annual gross (BRUTO)**",
        "es": "**Bruto anual (BRUTO)**",
    },
    "dossier.revenue.monthly_gross": {"en": "Monthly gross", "es": "Bruto mensual"},
    "dossier.revenue.artist_payout": {
        "en": "Artist payout (~74% of gross)",
        "es": "Pago al artista (~74% del bruto)",
    },
    "dossier.revenue.distributor_cut": {
        "en": "Distributor cut if signed (~26%)",
        "es": "Comisión del distribuidor si está firmado (~26%)",
    },
    "dossier.revenue.confidence_prefix": {
        "en": "**Confidence: {level}** — {reason}",
        "es": "**Confianza: {level}** — {reason}",
    },
    "dossier.revenue.disclaimer": {
        "en": (
            "*Predicts the artist's **total catalog** revenue across all platforms and "
            "all distributors — i.e. what the catalog is worth if FaroLatino had full "
            "rights. Distributor cut is what FaroLatino would actually earn under "
            "typical splits.*"
        ),
        "es": (
            "*Estima los ingresos del **catálogo completo** del artista a través de "
            "todas las plataformas y distribuidores — es decir, lo que valdría el "
            "catálogo si FaroLatino tuviera todos los derechos. La comisión del "
            "distribuidor es lo que FaroLatino realmente ganaría bajo los splits típicos.*"
        ),
    },
    "dossier.revenue.per_platform_header": {
        "en": "**Per-platform monthly contribution (BRUTO):**",
        "es": "**Contribución mensual por plataforma (BRUTO):**",
    },

    # ─── Reach row labels ────────────────────────────────────────────
    "dossier.reach.spotify": {"en": "Spotify", "es": "Spotify"},
    "dossier.reach.youtube": {"en": "YouTube", "es": "YouTube"},
    "dossier.reach.instagram": {"en": "Instagram", "es": "Instagram"},
    "dossier.reach.tiktok": {"en": "TikTok", "es": "TikTok"},
    "dossier.reach.monthly_listeners_suffix": {
        "en": "monthly listeners",
        "es": "oyentes mensuales",
    },
    "dossier.reach.followers_suffix": {"en": "followers", "es": "seguidores"},
    "dossier.reach.subscribers_suffix": {"en": "subscribers", "es": "suscriptores"},
    "dossier.reach.total_views_suffix": {
        "en": "total views",
        "es": "vistas totales",
    },
    "dossier.reach.engagement_label": {"en": "engagement", "es": "engagement"},

    # ─── Identity / metadata bullets ─────────────────────────────────
    "dossier.identity.career_stage": {"en": "Career stage", "es": "Etapa de carrera"},
    "dossier.identity.label": {"en": "Label", "es": "Sello"},
    "dossier.identity.genres": {"en": "Genres", "es": "Géneros"},
    "dossier.identity.tier_score": {
        "en": "**Tier: {tier}** · Prospect score: {score}/100 (confidence {confidence})",
        "es": "**Nivel: {tier}** · Puntaje de prospecto: {score}/100 (confianza {confidence})",
    },

    # ─── Catalog ─────────────────────────────────────────────────────
    "dossier.catalog.tracks_6m": {
        "en": "Tracks (last 6m)",
        "es": "Tracks (últimos 6m)",
    },
    "dossier.catalog.tracks_12m": {
        "en": "Tracks (last 12m)",
        "es": "Tracks (últimos 12m)",
    },
    "dossier.catalog.total_tracks": {
        "en": "Total tracks",
        "es": "Tracks totales",
    },
    "dossier.catalog.summary": {
        "en": "**{r6}** releases in last 6 months · **{r12}** in last 12 months · **{total}** tracks total",
        "es": "**{r6}** lanzamientos en los últimos 6 meses · **{r12}** en los últimos 12 meses · **{total}** tracks en total",
    },

    # ─── Similar / comps ─────────────────────────────────────────────
    "dossier.similar.empty": {
        "en": "*(no comparable artists surfaced — Chartmetric clustering and genre-search both empty)*",
        "es": "*(no se encontraron artistas comparables — Chartmetric no devolvió comps de clustering ni de género)*",
    },
    "dossier.similar.header_seed": {
        "en": "# Similar to {seed}",
        "es": "# Similares a {seed}",
    },
    "dossier.similar.no_neighbors": {
        "en": (
            "_No neighbors returned._ Chartmetric's similar-artists graph "
            "doesn't have data for this seed yet — try @similar on a more "
            "established artist, or @evaluate first to confirm the seed resolved."
        ),
        "es": (
            "_No se encontraron similares._ El grafo de Chartmetric aún no tiene "
            "datos para este artista — prueba @similar con uno más establecido, "
            "o usa @evaluate primero para confirmar que el artista se resolvió."
        ),
    },
    "dossier.similar.mix_prefix": {"en": "**Mix:**", "es": "**Mezcla:**"},
    "dossier.similar.tier_peers": {"en": "tier peers", "es": "del mismo nivel"},
    "dossier.similar.larger": {"en": "larger", "es": "más grandes"},
    "dossier.similar.smaller": {"en": "smaller", "es": "más chicos"},
    "dossier.similar.unknown": {"en": "unknown", "es": "desconocidos"},
    "dossier.similar.signed_yes": {"en": "yes", "es": "sí"},
    "dossier.similar.signed_no": {"en": "**no**", "es": "**no**"},
    "dossier.similar.monthly_suffix": {
        "en": "monthly listeners",
        "es": "oyentes mensuales",
    },

    # ─── Recommendation prose (per tier) ─────────────────────────────
    "dossier.reco.buy": {
        "en": "Active outreach. Lead profile in this tier — push to PROSPECT pipeline.",
        "es": "Contacto activo. Perfil líder en este nivel — moverlo al pipeline de PROSPECT.",
    },
    "dossier.reco.prospect": {
        "en": "Schedule a deeper look this week. Strong signals, watching for momentum confirmation.",
        "es": "Agendar un análisis profundo esta semana. Señales fuertes, esperando confirmación de momentum.",
    },
    "dossier.reco.watch": {
        "en": "Re-check quarterly. Holding pattern — signals not yet strong enough to chase.",
        "es": "Revisar cada trimestre. En espera — las señales aún no son lo suficientemente fuertes para perseguir.",
    },
    "dossier.reco.pass": {
        "en": "Skip. Not a fit on current criteria.",
        "es": "Descartar. No encaja con los criterios actuales.",
    },
    "dossier.reco.default": {
        "en": "Re-check next cycle.",
        "es": "Revisar en el próximo ciclo.",
    },
    "dossier.reco.locked": {
        "en": " Currently signed to **{label}** — no signing window unless contract status shifts.",
        "es": " Actualmente firmado con **{label}** — no hay ventana de firma a menos que cambie el estado del contrato.",
    },

    # ─── Legacy callout ──────────────────────────────────────────────
    "dossier.legacy.callout": {
        "en": (
            "⚠️ **Legacy / heritage catalog detected.** Revenue projection "
            "assumes active distribution. Real streams are likely far lower "
            "because Chartmetric's monthly_listeners count includes passive "
            "saved tracks. Treat the number as a ceiling, not an estimate."
        ),
        "es": (
            "⚠️ **Catálogo legado / herencia detectado.** La proyección de ingresos "
            "asume distribución activa. Los streams reales probablemente son mucho "
            "menores porque el conteo de oyentes mensuales de Chartmetric incluye "
            "tracks guardados pasivamente. Tratar el número como un techo, no una estimación."
        ),
    },

    # ─── Action block ────────────────────────────────────────────────
    "dossier.action.body": {
        "en": (
            "**Tier: {tier}**\n\n"
            "Use `/evaluate {name}` to drill in further, `/similar {name}` to map "
            "the competitive landscape, or `/compare {a} {b}` to put two prospects side-by-side."
        ),
        "es": (
            "**Nivel: {tier}**\n\n"
            "Usa `/evaluate {name}` para profundizar, `/similar {name}` para mapear "
            "el panorama competitivo, o `/compare {a} {b}` para comparar dos prospectos lado a lado."
        ),
    },

    # ─── Followup invite (chat-side bottom of dossier) ───────────────
    "dossier.followup_invite": {
        "en": (
            "---\n\n"
            "_Ask a follow-up about catalog, momentum, comps, or risk signals — "
            "e.g._ `is his catalog mostly evergreen or hit-driven?` _·_ "
            "`who in his tier is unsigned?` _·_ `what's his TikTok presence like?`"
        ),
        "es": (
            "---\n\n"
            "_Hazme una pregunta de seguimiento sobre el catálogo, momentum, comps o "
            "señales de riesgo — p. ej._ `¿su catálogo es mayormente evergreen o de hits?` _·_ "
            "`¿quién en su nivel está sin firmar?` _·_ `¿cómo es su presencia en TikTok?`"
        ),
    },

    # ─── Header subtitle (`stage / trend`) — formatting only ─────────
    "dossier.header.unknown": {"en": "Unknown", "es": "Desconocido"},

    # ─── v0.5.0 sound profile + content velocity ─────────────────────
    "dossier.section.sound_profile": {
        "en": "Sound profile",
        "es": "Perfil de sonido",
    },
    "dossier.section.content_velocity": {
        "en": "Content velocity",
        "es": "Velocidad de contenido",
    },
    "dossier.section.top_tracks": {
        "en": "Top tracks (by Spotify popularity)",
        "es": "Top tracks (por popularidad en Spotify)",
    },
    "dossier.col.popularity": {"en": "Popularity", "es": "Popularidad"},
    "dossier.col.cadence": {"en": "Cadence", "es": "Cadencia"},
    "dossier.col.trend": {"en": "Trend", "es": "Tendencia"},
    "dossier.cadence.accelerating": {
        "en": "accelerating",
        "es": "acelerando",
    },
    "dossier.cadence.steady": {"en": "steady", "es": "estable"},
    "dossier.cadence.decelerating": {
        "en": "decelerating",
        "es": "desacelerando",
    },
    "dossier.sound.danceability": {
        "en": "Danceability",
        "es": "Bailabilidad",
    },
    "dossier.sound.energy": {"en": "Energy", "es": "Energía"},
    "dossier.sound.tempo": {"en": "Tempo", "es": "Tempo"},
    "dossier.sound.summary": {
        "en": "Danceability **{dance}** · Energy **{energy}** · {tempo} BPM",
        "es": "Bailabilidad **{dance}** · Energía **{energy}** · {tempo} BPM",
    },
    "dossier.velocity.last_release": {
        "en": "Last release",
        "es": "Último lanzamiento",
    },
    "dossier.velocity.last_upload": {
        "en": "Last upload",
        "es": "Última subida",
    },
    "dossier.velocity.avg_views": {
        "en": "Avg views (last 3 videos)",
        "es": "Vistas promedio (últimos 3 videos)",
    },
    "dossier.velocity.like_ratio": {
        "en": "Like ratio",
        "es": "Ratio de likes",
    },
    "dossier.velocity.days_ago": {
        "en": "{n} days ago",
        "es": "hace {n} días",
    },
    "dossier.velocity.cadence_summary": {
        "en": "1 every {cadence} days · {trend}",
        "es": "1 cada {cadence} días · {trend}",
    },
    "dossier.velocity.spotify_label": {"en": "Spotify", "es": "Spotify"},
    "dossier.velocity.youtube_label": {"en": "YouTube", "es": "YouTube"},
    "dossier.catalog.cadence_extension": {
        "en": "· Latest: {n} days ago · cadence 1 every {cadence} days, {trend}",
        "es": "· Último: hace {n} días · cadencia 1 cada {cadence} días, {trend}",
    },
}


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    """Look up a translation by key. Falls back to English on miss.

    Pass ``**kwargs`` to substitute into the message via ``str.format``
    — e.g. ``t("dossier.identity.tier_score", lang, tier="WATCH",
    score=63, confidence="0.99")``.
    """
    lang = lang or DEFAULT_LANGUAGE
    entry = _MESSAGES.get(key)
    if not entry:
        # Programmer error — surface the key so it shows up in tests.
        return f"⟦missing:{key}⟧"
    msg = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or f"⟦missing:{key}:{lang}⟧"
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg
