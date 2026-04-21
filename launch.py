# launch.py
# Self-contained launcher for the Industry News webapp.
#
# Runs in two modes automatically:
#   - Normal (via .bat or .sh): spawns uvicorn via the venv Python
#     as a child process. Requires a .venv to be set up once.
#   - Frozen (PyInstaller bundle): runs uvicorn in-process on a
#     background thread. No venv or Python install needed by the user.
#
# The user never needs to touch a terminal —
# double-click "Launch Industry News.bat" (Windows)
# or "launch_macos.sh" (Mac).

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Detect whether we are running inside a PyInstaller frozen bundle.
# PyInstaller sets sys.frozen = True and sys._MEIPASS to the folder
# where it has extracted all bundled files (_internal/ in COLLECT mode).
# ---------------------------------------------------------------------------
_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # _MEIPASS is where server/, static/, data/ were extracted.
    # The user-facing .exe lives one level up in the install folder.
    _INTERNAL_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _EXE_DIR      = Path(sys.executable).parent
    PROJECT_ROOT  = _INTERNAL_DIR   # Python packages and assets live here
    _LOG_ROOT     = _EXE_DIR        # logs/ sits next to the .exe (writable)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
    _LOG_ROOT    = PROJECT_ROOT

os.chdir(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Logging — write to logs/launch.log AND print to console
# ---------------------------------------------------------------------------
LOGS_DIR = _LOG_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "launch.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("launcher")

# ---------------------------------------------------------------------------
# Network configuration
# ---------------------------------------------------------------------------
HOST     = "127.0.0.1"
PORT     = 8000
URL      = f"http://localhost:{PORT}"
HEALTH   = f"http://{HOST}:{PORT}/api/health"
MAX_WAIT = 30   # seconds to wait for server to become ready
POLL_INT = 0.5  # seconds between health-check polls

# ---------------------------------------------------------------------------
# Venv paths — only relevant when NOT running as a frozen bundle
# ---------------------------------------------------------------------------
if not _FROZEN:
    if sys.platform == "win32":
        _VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        _SETUP_HINT = (
            "    python -m venv .venv\n"
            "    .venv\\Scripts\\python.exe "
            "-m pip install -r requirements.txt"
        )
    else:
        _VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python3"
        _SETUP_HINT = (
            "    python3 -m venv .venv\n"
            "    .venv/bin/pip install -r requirements.txt"
        )


def _find_python() -> Path:
    """
    Return the venv Python executable.
    Only called when running outside a frozen bundle.
    Raises SystemExit with a friendly message if the venv is missing.
    """
    if _VENV_PY.exists():
        return _VENV_PY
    log.error(
        "Virtual environment not found at: %s\n"
        "Please run the following commands once in a terminal:\n%s",
        _VENV_PY,
        _SETUP_HINT,
    )
    input("\nPress Enter to close...")
    sys.exit(1)


def _wait_for_server(timeout: int) -> bool:
    """
    Poll the health endpoint until it responds 200 or timeout expires.
    Returns True if ready, False if timed out.
    """
    deadline = time.monotonic() + timeout
    attempt  = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(HEALTH, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        if attempt == 1:
            log.info("Waiting for server to start...")
        time.sleep(POLL_INT)
    return False


# ---------------------------------------------------------------------------
# Frozen mode — run uvicorn in-process on a background thread
# ---------------------------------------------------------------------------

def _start_server_frozen() -> object:
    """
    Import the FastAPI app and start uvicorn in a daemon thread.
    The direct import of server.main ensures PyInstaller bundles all
    of the server's transitive dependencies at build time.
    Returns the uvicorn.Server instance so the caller can stop it.
    """
    import uvicorn                       # noqa: PLC0415
    from server.main import app          # noqa: PLC0415  (triggers analysis)

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:

    log.info("=" * 55)
    log.info("  Industry News — Company Reports and Information Engine")
    log.info("=" * 55)
    log.info("Project root : %s", PROJECT_ROOT)
    log.info("URL          : %s", URL)
    log.info("")

    # -----------------------------------------------------------------------
    # FROZEN MODE  — PyInstaller bundle; no venv needed
    # -----------------------------------------------------------------------
    if _FROZEN:
        log.info("Starting server (this takes a few seconds)...")
        try:
            uvicorn_server = _start_server_frozen()
        except Exception as exc:
            log.error("Failed to start server: %s", exc)
            input("\nPress Enter to close...")
            sys.exit(1)

        ready = _wait_for_server(MAX_WAIT)
        if not ready:
            log.error(
                "Server did not start within %ds.\n"
                "Check %s for details.",
                MAX_WAIT, LOG_FILE,
            )
            uvicorn_server.should_exit = True
            input("\nPress Enter to close...")
            sys.exit(1)

        log.info("")
        log.info("Server is ready!")
        log.info("Opening browser at %s", URL)
        log.info("")
        log.info("Press Ctrl+C (or close this window) to stop.")
        log.info("")
        webbrowser.open(URL)

        def _shutdown_frozen(signum, frame):
            log.info("Shutting down...")
            uvicorn_server.should_exit = True
            sys.exit(0)

        signal.signal(signal.SIGINT,  _shutdown_frozen)
        signal.signal(signal.SIGTERM, _shutdown_frozen)

        try:
            while not uvicorn_server.should_exit:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutting down...")
            uvicorn_server.should_exit = True

    # -----------------------------------------------------------------------
    # NORMAL MODE  — running via .bat / .sh with a local venv
    # -----------------------------------------------------------------------
    else:
        import subprocess   # noqa: PLC0415

        python = _find_python()
        log.info("Python       : %s", python)
        log.info("")

        # --reload is intentionally OMITTED: it conflicts with OneDrive sync
        # because the file-system watcher sees OneDrive's continuous metadata
        # updates and restarts the server before it can bind.
        cmd = [
            str(python), "-m", "uvicorn",
            "server.main:app",
            "--host", HOST,
            "--port", str(PORT),
        ]

        log.info("Starting server (this takes a few seconds)...")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            log.error("Failed to launch uvicorn: %s", exc)
            input("\nPress Enter to close...")
            sys.exit(1)

        def _stream_output():
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    log.info("[server] %s", line)

        t = threading.Thread(target=_stream_output, daemon=True)
        t.start()

        ready = _wait_for_server(MAX_WAIT)
        if not ready:
            log.error(
                "Server did not start within %ds.\n"
                "Check %s for details.",
                MAX_WAIT, LOG_FILE,
            )
            proc.terminate()
            input("\nPress Enter to close...")
            sys.exit(1)

        log.info("")
        log.info("Server is ready!")
        log.info("Opening browser at %s", URL)
        log.info("")
        log.info("Press Ctrl+C (or close this window) to stop.")
        log.info("")
        webbrowser.open(URL)

        def _shutdown_normal(signum, frame):
            log.info("Shutting down...")
            proc.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT,  _shutdown_normal)
        signal.signal(signal.SIGTERM, _shutdown_normal)

        try:
            proc.wait()
        except KeyboardInterrupt:
            log.info("Shutting down...")
            proc.terminate()


if __name__ == "__main__":
    main()
