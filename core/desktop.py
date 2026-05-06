"""Native-window launcher for FaroAI.

Replaces the V1 "open a browser tab" UX with a chromeless OS-native
window so FaroAI looks and feels like a desktop app, not a website
pretending to be one. Used by ``python -m core`` (Phase 5) and
becomes the binary entry point in Phase 6 when py2app wraps the
whole thing into a single ``.app``.

Architecture: uvicorn runs in a daemon thread, pywebview owns the
main thread (required by Cocoa / Win32 GUI loops). When the window
closes, ``os._exit(0)`` tears the daemon thread + child sockets down
without waiting for atexit hooks.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
import webview

log = logging.getLogger(__name__)

# V1's port. We try this first so an existing user's bookmarks /
# muscle memory don't break, then fall back to whatever's free.
DEFAULT_PORT = 8501

# Window geometry. 1280×820 fits the chat + sidebar comfortably on a
# 13" Mac without dominating the screen; 960×600 is the floor before
# the layout starts wrapping awkwardly (chat input collides with the
# sidebar's collapsed icons).
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 820
MIN_SIZE = (960, 600)

# How long we'll wait for uvicorn to come up before showing a window
# pointing at a server that may never answer. 10s is generous —
# typical boot is <1s — but accommodates a slow first-import on a
# fresh py2app bundle.
HEALTH_TIMEOUT_S = 10.0


def _find_free_port(preferred: int = DEFAULT_PORT) -> int:
    """Return ``preferred`` if it's free, else an OS-assigned ephemeral port.

    ``socket.bind(("127.0.0.1", 0))`` makes the kernel pick a free
    port; reading ``getsockname()`` after bind gives us the actual
    number. Closing the socket then makes the port available for
    uvicorn to claim immediately. There's a microscopic race window
    where another process could grab the port between our close and
    uvicorn's bind, but in practice this never fires on a single-user
    machine.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
        except OSError:
            pass
        else:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_uvicorn(port: int) -> threading.Thread:
    """Launch uvicorn in a daemon thread.

    Daemon=True so the process exits with the GUI thread when the
    window closes; otherwise uvicorn would keep us alive until SIGTERM.
    Log level is bumped down to ``warning`` because the GUI doesn't
    show stdout — info-level access logs would just disappear into
    the void on bundled builds.
    """
    def _run() -> None:
        try:
            uvicorn.run(
                "api.main:app",
                host="127.0.0.1",
                port=port,
                log_level="warning",
                # Disable uvicorn's signal handlers so they don't fight
                # with pywebview / the macOS app bundle's own handlers.
                # Without this, Ctrl-C in dev mode sometimes leaves a
                # zombie uvicorn process the OS has to kill on logout.
                reload=False,
            )
        except Exception:
            log.exception("uvicorn crashed")

    thread = threading.Thread(target=_run, name="faroai-uvicorn", daemon=True)
    thread.start()
    return thread


def _wait_for_health(port: int, timeout_s: float = HEALTH_TIMEOUT_S) -> None:
    """Poll ``/api/health`` until it returns 200 or the timeout fires.

    Showing the window before uvicorn is ready leaves the user
    staring at a "this site can't be reached" error for the first
    half-second. The poll cadence is intentionally tight (50ms) since
    99% of boots resolve in ~500ms and the user-perceived delay is
    dominated by ``import api.main`` (which py2app makes worse).
    """
    deadline = time.time() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError(
        f"FaroAI backend didn't come up on port {port} within {timeout_s}s. "
        "Check the console for a uvicorn traceback."
    )


def start_app(*, debug: bool = False) -> None:
    """Boot the backend + open the native window. Blocks until close.

    Args:
        debug: when True, pywebview enables right-click → Inspect on
            the window (uses Web Inspector on macOS / DevTools on
            Windows). Off in production builds.
    """
    port = _find_free_port()
    _start_uvicorn(port)
    _wait_for_health(port)

    webview.create_window(
        title="FaroAI",
        url=f"http://127.0.0.1:{port}/",
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_size=MIN_SIZE,
        # Resizable + maximisable like a real app. Confirm-on-close
        # is intentionally off — the chat persists to localStorage on
        # every turn, so accidentally closing loses nothing.
        resizable=True,
        maximized=False,
    )

    # webview.start() takes over the main thread until the window
    # closes. Cocoa requires the GUI loop to run on the main thread
    # specifically — running uvicorn here and webview in a thread
    # would crash on macOS. The daemon-thread split is the only
    # arrangement that works on both Mac + Windows.
    webview.start(debug=debug)

    # Hard exit on close so the uvicorn daemon thread doesn't keep
    # the process alive (its socket listener can hold the port for
    # 30s+ otherwise, blocking a quick relaunch). os._exit skips
    # atexit hooks we don't have, so this is safe.
    os._exit(0)


if __name__ == "__main__":
    start_app(debug="--debug" in sys.argv)
