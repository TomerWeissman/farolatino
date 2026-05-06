"""Phase 1 re-export shim.

V1 published these symbols from ``core.claude_runner``. The
implementation moved to ``core.agent_runner`` (in-process, multi-
provider) but tests, scripts, and any third-party integration that
imported the legacy module keeps working through this shim. The shim
will be deleted in Phase 9 once we've shipped at least one signed
installer + update.
"""
from __future__ import annotations

from core.agent_runner import (  # noqa: F401
    THINKING_PREFIX,
    ClaudeRunnerError,
    run_claude_streaming,
)

__all__ = ["THINKING_PREFIX", "ClaudeRunnerError", "run_claude_streaming"]
