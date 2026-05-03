"""GET /api/skills, GET/PUT/POST/DELETE /api/skills/{slug}.

The Skills page in the frontend lets the user view, edit, create, and
delete skill markdown files. All ops target `.claude/skills/{slug}.md`.

Slug validation: alphanumeric + hyphens + underscores, lowercase, 2-32
chars. We refuse anything else to keep filename → slug → @prefix mapping
clean (no spaces, no `/`, no shell special chars).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from api.schemas import (
    SkillCreate,
    SkillDetail,
    SkillSummary,
    SkillUpdate,
)
from core.skill_registry import SKILLS_DIR, find_skill, list_skills

router = APIRouter()

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def _validate_slug(slug: str) -> str:
    """Reject anything that wouldn't make a clean filename."""
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
        SkillSummary(slug=s.slug, name=s.name or s.slug, description=s.description or "")
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
    )


@router.put("/skills/{slug}", response_model=SkillDetail)
def put_skill(slug: str, payload: SkillUpdate) -> SkillDetail:
    _validate_slug(slug)
    s = find_skill(slug)
    if not s:
        raise HTTPException(status_code=404, detail=f"skill '{slug}' not found")
    _validate_frontmatter(payload.full_markdown)
    if len(payload.full_markdown) > 200_000:
        raise HTTPException(status_code=413, detail="skill markdown >200kB; refusing to write")
    s.file_path.write_text(payload.full_markdown, encoding="utf-8")
    _invalidate_cache()
    return get_skill(slug)


@router.post("/skills", response_model=SkillDetail, status_code=201)
def post_skill(payload: SkillCreate) -> SkillDetail:
    _validate_slug(payload.slug)
    if find_skill(payload.slug):
        raise HTTPException(status_code=409, detail=f"skill '{payload.slug}' already exists")
    body = payload.body.strip() or _default_skill_body(payload.name)
    full_md = _format_full_markdown(payload.name, payload.description, body)
    _validate_frontmatter(full_md)
    target = Path(SKILLS_DIR) / f"{payload.slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(full_md, encoding="utf-8")
    _invalidate_cache()
    return get_skill(payload.slug)


@router.delete("/skills/{slug}", status_code=204)
def delete_skill(slug: str) -> None:
    _validate_slug(slug)
    s = find_skill(slug)
    if not s:
        raise HTTPException(status_code=404, detail=f"skill '{slug}' not found")
    s.file_path.unlink()
    _invalidate_cache()


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
