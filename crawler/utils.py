"""
crawler/utils.py
Small shared helpers for the crawler's commands: usage printing, a heartbeat
for long runs, and saving/reading raw runs for --from-file dev testing.
"""

import json
import logging
import shutil
import sys
import threading
from contextlib import contextmanager
import time
from datetime import datetime
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)

# Raw API responses, one file per run. Gitignore this folder.
RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"



def save_run(name: str, response: anthropic.types.Message) -> tuple[dict, Path]:
    """Write a response to runs/<name>-<timestamp>.json. Returns (response_dict, path)."""
    RUNS_DIR.mkdir(exist_ok=True)
    response_dict = response.model_dump()
    path = RUNS_DIR / f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    # utf-8 explicitly: Windows defaults to cp1252 and chokes on names like "Nestlé"
    path.write_text(json.dumps(response_dict, indent=2), encoding="utf-8")
    return response_dict, path

def load_run(path: str | Path) -> dict:
    """Read a saved run back for --from-file testing (no API call)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))

def extract_record(response_dict: dict, tool_name: str) -> dict | None:
    """Return the named tool's input from a response dict, or None if it was never called."""
    for block in response_dict["content"]:
        if block["type"] == "tool_use" and block["name"] == tool_name:
            return block["input"]
    return None

# How to choose:

# Style	                                When it's used
# Progress bar (tqdm)	                You know the total, like 50 companies
# Spinner or timer on one line	        Unknown duration, a person watching the terminal
# Dots, or a log line every N seconds   Output going to a log file or CI,
#                                           where lines can't be rewritten

@contextmanager
def heartbeat(every: float = 5.0):
    """Print a '.' every `every` seconds until the block exits.
 
    Covers silent stretches (model thinking, a search running server-side) so a
    long run visibly isn't hung. Daemon thread, so Ctrl+C still works.
    """
    stop = threading.Event()

    def beat():
        while not stop.wait(every):  # False on timeout, True once stop is set
            print(".", end="", flush=True)

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        print()



# ------------------------------------------------------------------
# Live status line
# ------------------------------------------------------------------
# One line at the bottom of the terminal, redrawn every second:
#     Running: Vetting 6sense 12s | Vetting Stripe 9s
# All status_timer blocks share it, so concurrent workers don't fight over the
# line. TickerConsoleHandler erases it before each log message, and the next
# tick redraws it underneath.

STILL_RUNNING_LOG_SECONDS = 30  # non-terminal output: one log line this often instead

# Everything below is guarded by _lock. RLock because a log call made while
# holding it re-enters through TickerConsoleHandler.emit on the same thread.
_lock = threading.RLock()
_active: dict[object, tuple[str, float]] = {}    # token -> (label, start time)
_ticker: threading.Thread | None = None
_drawn_len = 0    # characters currently on the status line, so they can be erased

def _clear_line() -> None:
    """Erase the status line.  Caller must hold _lock"""
    global _drawn_len   # pylint: disable=global-statement
    if _drawn_len:
        sys.stderr.write("\r" + " " * _drawn_len + "\r")
        sys.stderr.flush()
        _drawn_len = 0

def _draw(interactive: bool) -> None:
    """Redraw (terminal) or log (anything else) the running calls. Caller must hold _lock."""
    global _drawn_len   # pylint: disable=global-statement
    now = time.perf_counter()
    text = "Running: " + " | ".join(
        f"{label} {int(now - start)}s" for label, start in _active.values()
    )
    if not interactive:
        logger.info(text)
        return
    # Keep it to one row: a wrapped line can't be erased with \r.
    text = text[:shutil.get_terminal_size().columns - 1]
    _clear_line()
    sys.stderr.write(text)
    sys.stderr.flush()
    _drawn_len = len(text)

def _tick() -> None:
    """Ticker thread body: redraw until no status_timer block is active, then exit."""
    global _ticker # pylint: disable=global-statement
    # stderr, not stdout: it's the stream the console log handler writes to.
    interactive = sys.stderr.isatty()
    while True:
        time.sleep(1.0 if interactive else STILL_RUNNING_LOG_SECONDS)
        with _lock:
            if not _active:
                _ticker = None
                return
            _draw(interactive)

@contextmanager
def status_timer(label: str):
    """Show '<label> Ns' on the shared live status line while the block runs.

    Safe to use from several threads at once; each block adds one entry to the
    same line. In a terminal the line updates every second. When output isn't
    a terminal (Lambda/CloudWatch, redirected to a file) it logs one
    "Running: ..." line every STILL_RUNNING_LOG_SECONDS instead.

    No "done" line: the caller (run_with_pause) logs the finish and the time.
    Needs TickerConsoleHandler as the console log handler, or log lines will
    print on top of the status line.
    """
    global _ticker  # pylint: disable=global-statement
    token = object()  # unique key, so two blocks with the same label don't collide
    with _lock:
        _active[token] = (label, time.perf_counter())
        if _ticker is None:
            # Daemon thread, so Ctrl+C still works.
            _ticker = threading.Thread(target=_tick, daemon=True)
            _ticker.start()
    try:
        yield
    finally:
        with _lock:
            del _active[token]
            _clear_line()

class TickerConsoleHandler(logging.StreamHandler):
    """Console log handler that erases the live status line before each message.

    Set as the console handler's class in settings.LOGGING. Without it, a log
    line would start at the end of the status line instead of on its own row.
    """
    def emit(self, record):
        with _lock:
            _clear_line()
            super().emit(record)
