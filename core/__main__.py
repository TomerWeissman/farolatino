"""Entry point: ``python -m core`` opens FaroAI as a native desktop app.

In Phase 6 this becomes the binary entry point py2app/PyInstaller
freezes — the bundled ``.app`` runs ``python -m core`` under the hood.
Until then, source-mode users can launch the same UX with one command.

Pass ``--debug`` to enable right-click → Inspect on the window.
"""
from __future__ import annotations

import sys

from core.desktop import start_app

if __name__ == "__main__":
    start_app(debug="--debug" in sys.argv)
