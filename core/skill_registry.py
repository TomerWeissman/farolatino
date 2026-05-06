"""Skill registry — read skill markdown files via the overlay system.

V2: walks the user/code/bundled overlay so user-customized skills
survive code-only updates. ``Skill.source`` tells the UI whether the
file came from a user customization, a recent update, or the original
bundled default — used to render "edited locally" badges and the
"Reset to default" button.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

from core import overlay
from core.overlay import Source

# Back-compat alias. V1 callers (api/routes/skills, scripts) imported
# SKILLS_DIR directly. We resolve it lazily — the bundled location
# changes between source-mode and frozen .app, and even in source mode
# we now write to the user-overlay dir, not this path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"  # legacy bundled path; reads now go through overlay


@dataclass(frozen=True)
class Skill:
    """A FaroAI skill (single ``.md`` file with YAML frontmatter).

    Attributes:
        slug: filename stem (e.g. "evaluate"). What users type after `@`.
        name: human-readable name from frontmatter.
        description: one-liner shown in skill picker tooltips.
        body: full markdown body (after frontmatter).
        file_path: absolute path to the source file in whichever layer
            it resolved from.
        source: which overlay layer the file came from. ``user`` =
            customized by the user (write-protected from updates);
            ``update`` = latest from the FaroAI team (came in via a
            code-only update); ``default`` = original bundled version.
    """
    slug: str
    name: str
    description: str
    body: str
    file_path: Path
    source: Source


def _parse_skill(path: Path, source: Source) -> Skill:
    """Parse a single .md skill file. Tolerates missing frontmatter."""
    text = path.read_text(encoding="utf-8")
    slug = path.stem

    if not text.startswith("---"):
        return Skill(slug=slug, name=slug, description="", body=text, file_path=path, source=source)

    parts = text.split("---", 2)
    if len(parts) < 3:
        return Skill(slug=slug, name=slug, description="", body=text, file_path=path, source=source)

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
        source=source,
    )


@functools.lru_cache(maxsize=1)
def list_skills() -> list[Skill]:
    """Return all skills across the user/update/bundled overlay,
    alphabetized by slug. user/ wins on collisions.

    Cached for the process lifetime; ``api/routes/skills`` clears the
    cache on every write so the UI sees edits immediately.
    """
    found = overlay.list_in_category("skills", glob="*.md")
    skills = [
        _parse_skill(resolved.path, resolved.source)
        for filename, resolved in found.items()
    ]
    skills.sort(key=lambda s: s.slug)
    return skills


def find_skill(slug: str) -> Skill | None:
    """Lookup by slug (filename stem). Case-insensitive."""
    target = slug.lower().lstrip("@")
    for s in list_skills():
        if s.slug.lower() == target:
            return s
    return None
