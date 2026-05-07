"""Three-layer overlay filesystem for user-customizable assets.

Why this exists: when you ship a code update that includes a new
default ``evaluate.md``, you don't want it to clobber a user's
locally-edited version. Likewise, a brand-new skill the user wrote
should never be touched by an update. The pattern is borrowed from
basically every shippable app — VS Code (settings + user snippets),
browsers (extensions), Slack (custom emoji).

Three layers, walked in priority order on every read:

  1. **user/**   — the user's customizations. Edits + new skills +
                    user-installed connectors live here. Never touched
                    by updates.
  2. **code/**   — the latest defaults from the FaroAI team. Each
                    code-only update zip (Phase 6.5) extracts here.
                    Replaces whatever was there before.
  3. **bundled** — read-only defaults frozen in the .app at build
                    time. Only changes on a full reinstall.

All writes from PUT/POST endpoints go to ``user/``. Reads walk the
three layers and return whichever matches first; the caller can ask
which layer the result came from to render "edited locally" / "from
defaults" badges in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from core.paths import app_config_dir, resource_path


class Source(str, Enum):
    """Which layer a file resolved from. Surfaced to the UI so the
    user knows whether they're looking at their own customization,
    the latest update from us, or the original bundled default."""

    USER = "user"        # they edited or created it; updates won't touch
    UPDATE = "update"    # came from a code-only update (~/.../code/)
    DEFAULT = "default"  # came from the bundle


@dataclass(frozen=True)
class Resolved:
    """A file located somewhere in the overlay stack."""

    path: Path
    source: Source


# Subdirectory per category, relative to its layer root.
#
# Asymmetry note: bundled + code/ mirror the project tree (so a code
# update zip just extracts cleanly), while user/ is flatter (the user's
# own dir, not a code overlay — they don't see `.claude/` as
# meaningful). The category abstracts this so callers don't deal with
# the per-layer path differences.
_LAYER_PATHS: dict[str, dict[str, str]] = {
    "skills": {
        "default": ".claude/skills",
        "update": ".claude/skills",
        "user": "skills",
    },
    "persona": {
        # Persona is a single file, not a directory. The "path" here is
        # the file itself relative to the layer root.
        "default": "FAROAI.md",
        "update": "FAROAI.md",
        "user": "persona.md",
    },
    # Parallel Spanish persona — picked when ``preferences.language ==
    # "es"`` so the LLM responds in Spanish. Falls back to the English
    # ``persona`` if no Spanish file exists at any layer.
    "persona_es": {
        "default": "FAROAI.es.md",
        "update": "FAROAI.es.md",
        "user": "persona.es.md",
    },
    "prompts": {
        "default": "prompts",
        "update": "prompts",
        "user": "prompts",
    },
    "config": {
        "default": "config",
        "update": "config",
        "user": "config",
    },
    # Phase 5.5b: connectors get their own overlay so user-installed
    # connectors survive updates. Path layout matches Python module
    # structure so each layer can be added to sys.path directly.
    "connectors": {
        "default": "mcp_server/connectors",
        "update": "mcp_server/connectors",
        "user": "connectors",
    },
}


def _layer_roots() -> list[tuple[Source, Path]]:
    """Return the three layer roots in priority order (highest first).

    user/ wins; then code/ (update overlay); then the bundled tree.
    Resolved per-call so tests can flip ``FAROAI_CONFIG_DIR`` mid-run
    without a module reload.
    """
    cfg = app_config_dir()
    return [
        (Source.USER, cfg / "user"),
        (Source.UPDATE, cfg / "code"),
        (Source.DEFAULT, resource_path("")),
    ]


def _category_subpath(category: str, source: Source) -> str:
    try:
        return _LAYER_PATHS[category][source.value]
    except KeyError as exc:
        raise ValueError(f"Unknown overlay category: {category}") from exc


def category_dir(category: str, source: Source) -> Path:
    """Return the directory for a category in a specific layer.

    For file-categories like ``persona`` (single-file), this returns
    the parent directory; use ``resolve_file()`` to get the file
    itself.
    """
    layer_root = next(root for s, root in _layer_roots() if s == source)
    sub = _category_subpath(category, source)
    candidate = layer_root / sub
    # If the category is a single file (sub points at a .md, .yaml,
    # etc.), return its parent.
    if "." in sub.split("/")[-1]:
        return candidate.parent
    return candidate


def resolve(category: str, filename: str) -> Resolved | None:
    """Find ``filename`` in ``category`` across the layer stack.

    For directory categories (skills, prompts, config), ``filename`` is
    the leaf name including extension (e.g. ``"evaluate.md"``).
    For file categories (persona), ``filename`` is the layer-specific
    file name from ``_LAYER_PATHS`` — pass ``"FAROAI.md"`` and the
    function will find it in the right layer regardless of how each
    layer names it. Easier to use ``resolve_file(category)`` for those.
    """
    for source, root in _layer_roots():
        sub = _category_subpath(category, source)
        # Single-file category: the sub path IS the file.
        if "." in sub.split("/")[-1]:
            candidate = root / sub
        else:
            candidate = root / sub / filename
        if candidate.exists() and candidate.is_file():
            return Resolved(path=candidate, source=source)
    return None


def resolve_file(category: str) -> Resolved | None:
    """Convenience for single-file categories like ``persona``.

    Walks layers and returns whichever has the file. Each layer can
    name it differently (user puts ``persona.md`` in their dir, the
    bundled version is ``FAROAI.md``); the layer config in
    ``_LAYER_PATHS`` handles the name mapping.
    """
    for source, root in _layer_roots():
        sub = _category_subpath(category, source)
        candidate = root / sub
        if candidate.is_file():
            return Resolved(path=candidate, source=source)
    return None


def list_in_category(category: str, glob: str = "*.md") -> dict[str, Resolved]:
    """Walk all three layers and return ``{filename: Resolved}``.

    user/ wins on duplicate filenames. The dict's values carry the
    source layer so callers can render "edited locally" badges.
    Filename keys are stripped of the layer-specific path so a user's
    ``user/skills/evaluate.md`` and the bundled
    ``.claude/skills/evaluate.md`` collide on ``"evaluate.md"`` and
    the user copy wins.

    Useful for the Skills page — one call returns every available
    skill plus its source.
    """
    found: dict[str, Resolved] = {}
    for source, root in _layer_roots():
        sub = _category_subpath(category, source)
        # Single-file categories don't have a list semantic; bail.
        if "." in sub.split("/")[-1]:
            continue
        layer_dir = root / sub
        if not layer_dir.is_dir():
            continue
        for path in sorted(layer_dir.glob(glob)):
            if not path.is_file():
                continue
            key = path.name
            # First-write wins because we walk highest-priority layer first.
            if key not in found:
                found[key] = Resolved(path=path, source=source)
    return found


def user_path(category: str, filename: str) -> Path:
    """Return where this file would live if written by the UI.

    All PUT/POST writes go to ``user/``. For directory categories the
    file lands at ``user/<sub>/<filename>``; for single-file
    categories it lands at ``user/<sub>``. Caller is responsible for
    ``mkdir(parents=True, exist_ok=True)``.
    """
    cfg = app_config_dir()
    sub = _category_subpath(category, Source.USER)
    if "." in sub.split("/")[-1]:
        # Single-file category — filename arg is ignored, we use the
        # layer-specific file name.
        return cfg / "user" / sub
    return cfg / "user" / sub / filename


def is_user_customized(category: str, filename: str) -> bool:
    """True iff this file currently has a user-layer copy."""
    return user_path(category, filename).exists()


def reset_to_default(category: str, filename: str) -> bool:
    """Delete the user-layer copy so the next read falls through to
    code/ or bundled/. Returns True iff something was actually deleted.
    Idempotent: calling on a non-customized file is a no-op.
    """
    target = user_path(category, filename)
    if not target.exists():
        return False
    target.unlink()
    return True
