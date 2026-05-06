"""GET /api/skills, GET/PUT/POST/DELETE /api/skills/{slug}, POST /api/skills/{slug}/reset.

V2 overlay model: writes always go to the user layer
(``~/Library/Application Support/FaroAI/user/skills/``). Reads walk
user → update → bundled and report which layer the file came from
(``source`` field) so the UI can render badges.

- ``DELETE`` removes the user-layer copy only — if a default exists
  underneath, the skill remains visible (just no longer customized).
  The undocumented sub-route ``POST /skills/{slug}/reset`` is the
  same operation phrased as "reset to default" for clarity.
- ``POST`` (create new) writes to the user layer — these are user-
  authored skills that updates won't touch.

Slug validation: alphanumeric + hyphens + underscores, lowercase, 2-32
chars. We refuse anything else to keep filename → slug → @prefix mapping
clean (no spaces, no `/`, no shell special chars).
"""
from __future__ import annotations

import re

import yaml
from fastapi import APIRouter, HTTPException

from api.schemas import (
    SkillCreate,
    SkillDetail,
    SkillSummary,
    SkillUpdate,
)
from core import overlay
from core.overlay import Source
from core.skill_registry import find_skill, list_skills

router = APIRouter()

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def _validate_slug(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="slug must be lowercase alphanumeric (with -/_) and 2-32 chars",
        )
    return slug


def _format_full_markdown(name: str, description: str, body: str) -> str:
    """Reassemble frontmatter + body. Pass-through if `body` already
    starts with frontmatter (caller editing the raw thing themselves)."""
    if body.lstrip().startswith("---"):
        return body
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body.lstrip()}"


def _validate_frontmatter(full_markdown: str) -> None:
    """Raise 400 if the frontmatter doesn't parse cleanly."""
    if not full_markdown.lstrip().startswith("---"):
        raise HTTPException(
            status_code=400,
            detail="skill must start with YAML frontmatter (--- … ---)",
        )
    parts = full_markdown.split("---", 2)
    if len(parts) < 3:
        raise HTTPException(
            status_code=400,
            detail="frontmatter has no closing ---",
        )
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"frontmatter YAML error: {exc}",
        ) from exc
    if not isinstance(meta, dict):
        raise HTTPException(
            status_code=400,
            detail="frontmatter must be a YAML mapping",
        )


def _invalidate_cache() -> None:
    """Skills are lru_cached for process lifetime — clear after writes."""
    list_skills.cache_clear()


@router.get("/skills", response_model=list[SkillSummary])
def get_skills() -> list[SkillSummary]:
    return [
        SkillSummary(
            slug=s.slug,
            name=s.name or s.slug,
            description=s.description or "",
            source=s.source.value,
        )
        for s in list_skills()
    ]


@router.get("/skills/{slug}", response_model=SkillDetail)
def get_skill(slug: str) -> SkillDetail:
    s = find_skill(slug)
    if not s:
        raise HTTPException(status_code=404, detail=f"skill '{slug}' not found")
    return SkillDetail(
        slug=s.slug,
        name=s.name or s.slug,
        description=s.description or "",
        body=s.body,
        full_markdown=s.file_path.read_text(encoding="utf-8"),
        source=s.source.value,
    )


@router.put("/skills/{slug}", response_model=SkillDetail)
def put_skill(slug: str, payload: SkillUpdate) -> SkillDetail:
    """Edit a skill — writes to the user layer regardless of where the
    current version came from. Once edited, future updates won't
    touch it.
    """
    _validate_slug(slug)
    if not find_skill(slug):
        raise HTTPException(status_code=404, detail=f"skill '{slug}' not found")
    _validate_frontmatter(payload.full_markdown)
    if len(payload.full_markdown) > 200_000:
        raise HTTPException(status_code=413, detail="skill markdown >200kB; refusing to write")

    target = overlay.user_path("skills", f"{slug}.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.full_markdown, encoding="utf-8")
    _invalidate_cache()
    return get_skill(slug)


@router.post("/skills", response_model=SkillDetail, status_code=201)
def post_skill(payload: SkillCreate) -> SkillDetail:
    """Create a brand-new user skill. Lives in the user layer — never
    touched by updates."""
    _validate_slug(payload.slug)
    if find_skill(payload.slug):
        raise HTTPException(status_code=409, detail=f"skill '{payload.slug}' already exists")
    body = payload.body.strip() or _default_skill_body(payload.name)
    full_md = _format_full_markdown(payload.name, payload.description, body)
    _validate_frontmatter(full_md)

    target = overlay.user_path("skills", f"{payload.slug}.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(full_md, encoding="utf-8")
    _invalidate_cache()
    return get_skill(payload.slug)


@router.delete("/skills/{slug}", status_code=204)
def delete_skill(slug: str) -> None:
    """Delete behavior depends on where the skill lives:

    - User-layer customization: deletes the user copy. If a default
      exists underneath (update or bundled), the skill remains
      visible — just no longer customized. Equivalent to
      "Reset to default" for skills with a default underneath.
    - User-only skill (no default underneath): removes it entirely.
    - Default-only skill with no user copy: refuse — defaults can't
      be deleted, only overridden.
    """
    _validate_slug(slug)
    s = find_skill(slug)
    if not s:
        raise HTTPException(status_code=404, detail=f"skill '{slug}' not found")
    if s.source != Source.USER:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{slug}' is a default skill — can't delete. Edit it to override, "
                "or POST /skills/{slug}/reset has no effect because it's already default."
            ),
        )
    overlay.reset_to_default("skills", f"{slug}.md")
    _invalidate_cache()


@router.post("/skills/{slug}/reset", response_model=SkillDetail | None)
def reset_skill(slug: str) -> SkillDetail | None:
    """Drop the user-layer customization so the next read falls
    through to whatever default is underneath.

    Returns the now-default skill if one exists underneath, else
    ``None`` (the skill was user-only and has been deleted entirely).
    """
    _validate_slug(slug)
    overlay.reset_to_default("skills", f"{slug}.md")
    _invalidate_cache()
    s = find_skill(slug)
    if s is None:
        # Skill was user-only and has been removed entirely.
        return None
    return get_skill(slug)


def _default_skill_body(name: str) -> str:
    """Bootstrap body for a brand-new skill — gives the user a starting
    template instead of a blank page."""
    return (
        f"# {name}\n\n"
        f"When the user runs `@{name.lower().replace(' ', '-')} {{argument}}`:\n\n"
        f"1. Describe step 1 here.\n"
        f"2. Describe step 2 here.\n"
        f"3. Present the result.\n\n"
        f"## Rules\n\n"
        f"- Add any tool restrictions or refusals here.\n"
    )
