"""Skill registry — read `.claude/skills/*.md` and expose name + description.

Used by the chat UI's skill picker (sidebar list) and by the future @-autocomplete
component. Parses YAML frontmatter from each skill file; tolerates skills that
don't have full frontmatter (falls back to filename stem for `name`).
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"


@dataclass(frozen=True)
class Skill:
    """A Claude Code skill defined in `.claude/skills/<slug>.md`.

    Attributes:
        slug: filename stem (e.g. "evaluate"). This is what users type after `@`.
        name: human-readable name from frontmatter (e.g. "Evaluate Artist").
        description: short one-liner shown in skill picker tooltips.
        body: full skill markdown body (after frontmatter). Reserved for
              potential future use; not surfaced in the UI.
        file_path: absolute path to the .md file.
    """
    slug: str
    name: str
    description: str
    body: str
    file_path: Path


def _parse_skill(path: Path) -> Skill:
    """Parse a single .md skill file. Tolerates missing frontmatter."""
    text = path.read_text(encoding="utf-8")
    slug = path.stem  # e.g. "evaluate"

    if not text.startswith("---"):
        return Skill(slug=slug, name=slug, description="", body=text, file_path=path)

    # Frontmatter is between the first two `---` lines.
    parts = text.split("---", 2)
    if len(parts) < 3:
        return Skill(slug=slug, name=slug, description="", body=text, file_path=path)

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}

    return Skill(
        slug=slug,
        name=str(meta.get("name", slug)).strip() or slug,
        description=str(meta.get("description", "")).strip(),
        body=parts[2].lstrip("\n"),
        file_path=path,
    )


@functools.lru_cache(maxsize=1)
def list_skills() -> list[Skill]:
    """Return all skills from `.claude/skills/`, alphabetized by slug.

    Cached for the process lifetime — restart the Streamlit app to pick up
    edits. Slug-sorted (not name-sorted) so behavior is predictable for
    autocomplete: typing `@e` after `@` matches `evaluate` before `Evaluate Artist`.
    """
    if not SKILLS_DIR.exists():
        return []
    skills = [
        _parse_skill(p)
        for p in sorted(SKILLS_DIR.glob("*.md"))
        if p.is_file()
    ]
    return skills


def find_skill(slug: str) -> Skill | None:
    """Lookup by slug (filename stem). Case-insensitive."""
    target = slug.lower().lstrip("@")
    for s in list_skills():
        if s.slug.lower() == target:
            return s
    return None
