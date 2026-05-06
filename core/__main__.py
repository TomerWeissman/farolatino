"""Entry point: ``python -m core`` opens FaroAI as a native desktop app.

This is what py2app/PyInstaller freezes as the binary entry point —
the bundled ``.app`` runs this module under the hood. Source-mode
users get the same UX from one command.

CRITICAL — code-loading hook for Phase 6.5 in-app updates:

Before importing ``core.desktop`` (which transitively imports our
whole codebase), we add the user-data ``code/`` directory to
``sys.path`` if it exists and contains a newer version than the
bundle. That way, a ~5 MB code zip extracted into
``~/Library/Application Support/FaroAI/code/`` overrides the bundled
code without a full reinstall.

This hook MUST be in the very first bundle shipped to users (v0.2.0).
If we ship without it, a v0.2.0 → v0.2.1 update would require a
full reinstall every time — defeating the whole 6.5 point.

Pass ``--debug`` to enable right-click → Inspect on the window.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _wire_user_code_overlay() -> None:
    """If ``~/Library/Application Support/FaroAI/code/`` exists and
    contains a valid manifest, prepend it to ``sys.path`` so its
    modules win over bundled ones.

    CRITICAL: this function MUST NOT import any module from the
    ``core`` package. As soon as ``core`` lands in ``sys.modules``,
    the bundle's version is cached and the overlay can never take
    over. We resolve the user-data dir path manually using stdlib
    (the same logic as ``core.paths.app_config_dir`` but inlined).

    Compatibility check: future versions can extend the manifest with
    minimum bundled-SDK declarations. For v0.2.0 we just check the
    manifest exists + has a ``version`` field; full compatibility
    enforcement lives in ``core/updater.py`` BEFORE extraction (so an
    incompatible zip never lands in ``code/``).

    Failure-tolerant: any error drops back to bundled code. Better to
    run an old version than fail to launch.
    """
    try:
        import json
        import os
        import platform

        # FAROAI_CONFIG_DIR override (used by tests + dev installs).
        override = os.environ.get("FAROAI_CONFIG_DIR")
        if override:
            cfg = Path(override).expanduser().resolve()
        elif platform.system() == "Darwin":
            cfg = Path.home() / "Library" / "Application Support" / "FaroAI"
        elif platform.system() == "Windows":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            cfg = Path(base) / "FaroAI"
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
            cfg = Path(base) / "faroai"

        code_dir = cfg / "code"
        if not code_dir.is_dir():
            return

        manifest_path = code_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            return
        if "version" not in manifest:
            return

        # Prepend so user-overlay modules shadow bundled ones.
        # MUST happen before any `from core.X import Y` below.
        sys.path.insert(0, str(code_dir))
    except Exception:
        # Defensive — if anything goes wrong, run the bundled code.
        return


_wire_user_code_overlay()

# All imports below this line MAY now be resolved from the user
# overlay if it's installed. The first import sets the precedent.
from core.desktop import start_app  # noqa: E402

if __name__ == "__main__":
    start_app(debug="--debug" in sys.argv)
