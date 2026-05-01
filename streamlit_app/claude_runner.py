"""Claude Code subprocess wrapper for the chat UI.

Spawns `claude --print --verbose --output-format stream-json` with the
project root as cwd, so Claude Code resolves skills (`.claude/skills/`)
and MCP servers from the user's existing configuration. Yields text
chunks suitable for `st.write_stream`.

Why a subprocess: keeps skill discovery, MCP routing, and auth in
Claude Code's hands. We don't reimplement any of it.

Why `--verbose`: required when `--output-format stream-json` is set
(Claude Code refuses without it).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ClaudeRunnerError(Exception):
    """Surfaced to the chat UI as a system message."""


def _claude_path() -> str | None:
    """Locate the `claude` binary on PATH."""
    return shutil.which("claude")


def run_claude_streaming(prompt: str, *, max_turns: int | None = None) -> Iterator[str]:
    """Run `claude --print` and yield text deltas as they arrive.

    Args:
        prompt: the user's chat message (already includes any `@skill` prefix).
        max_turns: optional safety cap on agentic loops.

    Yields:
        Text chunks. Concatenate all chunks for the full response.

    Raises:
        ClaudeRunnerError: if `claude` is not on PATH, or the subprocess
            fails before producing any output.
    """
    binary = _claude_path()
    if binary is None:
        raise ClaudeRunnerError(
            "Claude Code is not installed (no `claude` binary on PATH). "
            "Install from https://claude.com/claude-code, then run `claude login`."
        )

    cmd = [binary, "--print", "--verbose", "--output-format", "stream-json"]
    if max_turns is not None:
        cmd.extend(["--max-turns", str(max_turns)])
    cmd.append(prompt)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered so we get events as they arrive
        )
    except OSError as exc:
        raise ClaudeRunnerError(f"Failed to spawn `claude`: {exc}") from exc

    try:
        for raw_line in proc.stdout or []:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Tolerate non-JSON noise (Claude Code sometimes emits
                # warnings or progress lines that aren't proper events).
                continue

            for chunk in _extract_text(event):
                yield chunk
    finally:
        proc.wait(timeout=5)

    if proc.returncode != 0:
        stderr = (proc.stderr.read() if proc.stderr else "").strip()
        if "not authenticated" in stderr.lower() or "login" in stderr.lower():
            raise ClaudeRunnerError(
                "Claude Code is not logged in. Open a terminal and run `claude login`."
            )
        raise ClaudeRunnerError(
            f"Claude Code exited with code {proc.returncode}.\n{stderr[:400]}"
        )


def _extract_text(event: dict) -> Iterator[str]:
    """Pull user-visible text out of one stream-json event.

    Yields nothing for system / rate_limit / result / tool events that
    aren't meant for the chat bubble. The `result` event contains a
    consolidated copy of the final message, which would duplicate the
    `assistant` text — we ignore it.
    """
    etype = event.get("type")

    if etype == "assistant":
        message = event.get("message") or {}
        for block in message.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "")
                if text:
                    yield text
            elif btype == "tool_use":
                # Surface tool invocations as italicized status lines so the
                # user sees what's happening during long agentic runs.
                tool_name = block.get("name", "tool")
                yield f"\n\n_using `{tool_name}`..._\n\n"

    elif etype == "user":
        # Tool result going back into Claude — don't show in chat.
        return

    # Other types (system/init, rate_limit_event, result, error) are
    # intentionally skipped: either metadata or duplicates of assistant text.
