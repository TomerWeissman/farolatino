"""Claude Code subprocess wrapper for the chat UI.

Spawns `claude --print --verbose --output-format stream-json` with the
project root as cwd, so Claude Code resolves skills (`.claude/skills/`)
and MCP servers from the user's existing configuration. Yields text
chunks for the FastAPI SSE chat endpoint to relay to the browser.

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
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = PROJECT_ROOT / ".mcp.json"
PERSONA_PATH = PROJECT_ROOT / "FAROAI.md"


def _load_persona() -> str:
    """Read FAROAI.md so the model answers as the FaroAI A&R assistant.

    Re-read on every chat turn — edits to FAROAI.md take effect on the next
    message with no restart required. Returns "" silently if the file is
    missing (we fall back to Claude Code's default behavior).
    """
    try:
        return PERSONA_PATH.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return ""


class ClaudeRunnerError(Exception):
    """Surfaced to the chat UI as a system message."""


def _claude_path() -> str | None:
    return shutil.which("claude")


# --- Per-skill profiles -----------------------------------------------------
# Composite tools (one server-side tool that does the whole pipeline) get a
# tight allowlist and zero thinking budget so the model can't cascade into
# Bash/Agent retries. Generic prompts (no @skill) keep the full toolbox.

_DEFAULT_ALLOWED_TOOLS = [
    "mcp__farolatino__cache_clear",
    "mcp__farolatino__cache_get",
    "mcp__farolatino__cache_set",
    "mcp__farolatino__compute_prospect_score",
    "mcp__farolatino__discover_artists",
    "mcp__farolatino__discover_artists_multi_country",
    "mcp__farolatino__estimate_revenue",
    "mcp__farolatino__evaluate_artist",
    "mcp__farolatino__find_similar_artists",
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
]

_SKILL_PROFILES: dict[str, dict] = {
    "@evaluate": {
        "allowed_tools": [
            "mcp__farolatino__evaluate_artist",
            "mcp__farolatino__search_artist_by_url",  # URL-direct entry
            "Read",       # for prompts/*.txt narrative templates only
            "ToolSearch", # in case Claude Code defers tool schemas
        ],
        "max_thinking_tokens": 0,
    },
    "@similar": {
        "allowed_tools": [
            "mcp__farolatino__find_similar_artists",
            "mcp__farolatino__search_artist_by_url",
            "ToolSearch",
        ],
        "max_thinking_tokens": 0,
    },
}


def _resolve_skill_profile(prompt: str) -> dict:
    """Return per-skill flags. Falls back to the generic profile."""
    head = prompt.strip().lower().split()[0] if prompt.strip() else ""
    if head in _SKILL_PROFILES:
        return _SKILL_PROFILES[head]
    return {
        "allowed_tools": _DEFAULT_ALLOWED_TOOLS,
        "max_thinking_tokens": 8000,
    }


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

    # Per-skill profile: skills with deterministic composite tools (e.g.
    # @evaluate → mcp__farolatino__evaluate_artist) get a TIGHT allowlist
    # and zero thinking budget — the pipeline is server-side, the model
    # just needs to call one tool and present the result. Letting the
    # model see Bash/Agent/Glob in this mode invites cascading retries
    # (we observed a single @evaluate run cost $0.88 / 354s / 19 tool
    # calls when the model fell back to Agent + Bash to reshape data).
    #
    # The `--allowed-tools <tools...>` flag is variadic — pass each
    # tool as a separate arg and the parser consumes the trailing prompt
    # too. So we pass ONE space-separated string instead.
    profile = _resolve_skill_profile(prompt)
    cmd.extend(["--allowed-tools", " ".join(profile["allowed_tools"])])
    cmd.extend(["--max-thinking-tokens", str(profile["max_thinking_tokens"])])

    # Inject the FaroAI persona + today's date as the appended system prompt.
    # FAROAI.md is the user-editable memory file at the project root: it
    # defines the assistant's identity, scope, capabilities, and what it
    # should refuse. Without this, the model answers as generic Claude Code
    # ("I'm Claude, an AI assistant...") instead of as FaroAI.
    today = date.today().isoformat()
    persona = _load_persona()
    date_note = (
        f"Today's date is {today}. When you see release dates, compare them "
        f"to today to determine whether they are past or upcoming. Treat "
        f"dates earlier than today as already-released."
    )
    appended = f"{persona}\n\n---\n\n{date_note}" if persona else date_note
    cmd.extend(["--append-system-prompt", appended])

    if max_turns is not None:
        cmd.extend(["--max-turns", str(max_turns)])

    # `--` end-of-flags marker. Required because `--allowed-tools <tools...>`
    # is a variadic flag in commander.js — it greedily consumes every
    # following positional arg, including our prompt. Without `--`, a
    # subprocess invocation like
    #   claude ... --allowed-tools "tool1 tool2" "@evaluate Bad Bunny"
    # results in Claude Code seeing no prompt at all and failing with
    # "Input must be provided either through stdin or as a prompt argument".
    # Verified with isolated A/B tests: present `--` always works, absent
    # `--` always fails when --allowed-tools is in play.
    cmd.append("--")
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
            # Put claude --print + any children (notably the mcp_server it
            # spawns) in their own process group. This lets us kill the
            # whole group on completion — without it, an orphaned
            # mcp_server child can keep the stdout pipe write-end open
            # indefinitely, hanging our reader loop forever (real bug
            # observed in production).
            start_new_session=True,
        )
    except OSError as exc:
        raise ClaudeRunnerError(f"Failed to spawn `claude`: {exc}") from exc

    # Watchdog: when claude --print exits, kill its process group AND every
    # tracked descendant PID. The pgid kill (claude calls setsid() because
    # of start_new_session=True, so pgid == proc.pid) handles the common
    # case where mcp_server inherits claude's group. The PID-by-PID kill
    # is defense-in-depth: an MCP server that calls setsid() itself, or
    # double-forks, would escape the group — so we poll the tree while
    # claude is alive and remember every descendant we see, since once
    # claude exits its children get reparented to launchd and can't be
    # found by ppid traversal anymore.
    pgid = proc.pid
    descendants: set[int] = set()

    def _walk_descendants(root: int) -> set[int]:
        """Return all transitive descendants of root via `pgrep -P`."""
        found: set[int] = set()
        frontier = [root]
        while frontier:
            nxt: list[int] = []
            for p in frontier:
                try:
                    out = subprocess.check_output(
                        ["pgrep", "-P", str(p)],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    ).strip()
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
                for token in out.split():
                    if token.isdigit():
                        cpid = int(token)
                        if cpid not in found:
                            found.add(cpid)
                            nxt.append(cpid)
            frontier = nxt
        return found

    def _kill_all(sig: int) -> None:
        for pid in list(descendants):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _watchdog() -> None:
        # Poll until claude --print exits, accumulating descendants.
        while True:
            descendants.update(_walk_descendants(proc.pid))
            try:
                proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
        # Final sweep in case anything was spawned just before exit.
        descendants.update(_walk_descendants(proc.pid))

        _kill_all(signal.SIGTERM)
        time.sleep(0.5)
        _kill_all(signal.SIGKILL)

        # Close stdout so any blocking readline() returns empty string.
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass

    threading.Thread(target=_watchdog, daemon=True).start()

    started_at = time.time()
    # Surface the actual command line as a synthetic _debug_cmd event so the
    # run-log captures exactly what was executed. Saved last debugging cycle
    # by exposing the variadic-flag bug in --allowed-tools. Cheap to keep on.
    if on_event is not None:
        try:
            on_event({"type": "_debug_cmd", "argv": cmd})
        except Exception:
            pass

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
        # Belt-and-suspenders: ensure claude AND every tracked descendant
        # is gone even if the watchdog hasn't fired yet (e.g. the iterator
        # was abandoned by the caller).
        descendants.update(_walk_descendants(proc.pid))
        _kill_all(signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _kill_all(signal.SIGKILL)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    if proc.returncode != 0:
        stderr = (proc.stderr.read() if proc.stderr else "").strip()
        if "not authenticated" in stderr.lower() or "login" in stderr.lower():
            raise ClaudeRunnerError(
                "Claude Code is not logged in. Open a terminal and run `claude login`."
            )
        raise ClaudeRunnerError(
            f"Claude Code exited with code {proc.returncode}.\n{stderr[:400]}"
        )


# Sentinel prefix that marks a chunk as a thinking delta rather than visible
# response text. The chat view splits on this and routes thinking deltas to
# the collapsible Reasoning panel. Chosen to be unlikely to appear in real
# model output but human-readable if it ever leaks through.
THINKING_PREFIX = "\x01THINK\x01"


def _extract_text(event: dict) -> Iterator[str]:
    """Pull user-visible text out of one stream-json event.

    Yields plain text deltas for assistant text blocks; thinking-block deltas
    are prefixed with THINKING_PREFIX so the consumer can split them out.
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
            elif btype == "thinking":
                # Claude's stream-json delivers full thinking blocks (not
                # incremental deltas) per assistant event. Prefix the whole
                # block; chat.py reassembles them in render order.
                thinking = block.get("thinking", "")
                if thinking:
                    yield f"{THINKING_PREFIX}{thinking}"
            elif btype == "tool_use":
                tool_name = block.get("name", "tool")
                yield f"\n\n_using `{tool_name}`..._\n\n"
