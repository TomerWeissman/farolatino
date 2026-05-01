"""Claude Code subprocess wrapper for the chat UI.

Spawns `claude --print --verbose --output-format stream-json` with the
project root as cwd, so Claude Code resolves skills (`.claude/skills/`)
and MCP servers from the user's existing configuration. Yields text
chunks suitable for `st.write_stream`.

Why a subprocess: keeps skill discovery, MCP routing, and auth in
Claude Code's hands. We don't reimplement any of it.

Why `--verbose`: required when `--output-format stream-json` is set.

Why `--mcp-config`: makes the FaroLatino MCP server self-contained per
snapshot. The launcher (start.command / start.bat) writes a fresh
`.mcp.json` at startup with absolute paths into the snapshot's venv,
so Claude Code can spin up our MCP tools without depending on a
user-scoped registration.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = PROJECT_ROOT / ".mcp.json"


class ClaudeRunnerError(Exception):
    """Surfaced to the chat UI as a system message."""


def _claude_path() -> str | None:
    return shutil.which("claude")


def run_claude_streaming(
    prompt: str,
    *,
    max_turns: int | None = None,
    on_event: callable | None = None,
) -> Iterator[str]:
    """Run `claude --print` and yield text deltas as they arrive.

    Args:
        prompt: the user's chat message (already includes any `@skill` prefix).
        max_turns: optional safety cap on agentic loops.
        on_event: optional callback invoked for every parsed JSON event from
            stream-json (system, assistant, user/tool_result, result, ...).
            Used by the run-log telemetry to capture full traces.

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
    if MCP_CONFIG_PATH.exists():
        # `--strict-mcp-config` ensures we use ONLY the FaroLatino MCP
        # server — no inheritance from the user's global Claude Code
        # config (so a tester's machine doesn't drag in their personal
        # Gmail/Notion MCP servers, for example).
        cmd.extend(["--mcp-config", str(MCP_CONFIG_PATH), "--strict-mcp-config"])

    # Pre-authorize the tools each skill needs. Without this, claude --print
    # asks for permission interactively (which hangs because there's no
    # interactive input stream). We allow all FaroLatino MCP tools plus
    # read-only file ops + Bash (the calibrate skill shells out). We do NOT
    # allow Edit/Write/NotebookEdit so a skill can't accidentally rewrite
    # the codebase.
    #
    # The CLI's `--allowed-tools <tools...>` flag is variadic — pass each
    # tool as a separate arg and the parser consumes the trailing prompt
    # too. So we pass ONE space-separated string instead.
    allowed = " ".join([
        "mcp__farolatino__cache_clear",
        "mcp__farolatino__cache_get",
        "mcp__farolatino__cache_set",
        "mcp__farolatino__compute_prospect_score",
        "mcp__farolatino__discover_artists",
        "mcp__farolatino__discover_artists_multi_country",
        "mcp__farolatino__estimate_revenue",
        "mcp__farolatino__generate_dossier",
        "mcp__farolatino__get_artist_data",
        "mcp__farolatino__get_profile",
        "mcp__farolatino__list_profiles",
        "mcp__farolatino__load_config",
        "mcp__farolatino__route_alert",
        "mcp__farolatino__search_artist_by_url",
        "mcp__farolatino__search_artists",
        "Read", "Glob", "Grep", "ToolSearch",
        "Bash",
    ])
    cmd.extend(["--allowed-tools", allowed])

    if max_turns is not None:
        cmd.extend(["--max-turns", str(max_turns)])
    cmd.append(prompt)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            # Detach stdin: claude waits on stdin if it isn't redirected,
            # which causes a 3s timeout and (in some configurations) a
            # non-zero exit even when --print is given the prompt as an arg.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise ClaudeRunnerError(f"Failed to spawn `claude`: {exc}") from exc

    started_at = time.time()
    try:
        for raw_line in proc.stdout or []:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    # Telemetry failures must never crash the chat.
                    pass

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
    """Pull user-visible text out of one stream-json event."""
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
                tool_name = block.get("name", "tool")
                yield f"\n\n_using `{tool_name}`..._\n\n"
