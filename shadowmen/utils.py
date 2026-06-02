import threading
import shutil
import subprocess
import os
import logging

log = logging.getLogger(__name__)

# Module-level lock for thread-safe initialization
_wmctrl_lock = threading.Lock()
_wmctrl_available: bool | None = None
_MIN_WINDOW_SIZE: int = 80          # Minimum width/height to be "reasonably-sized"
_FULLSCREEN_MARGIN: int = 10        # Pixels of tolerance for fullscreen detection
_WMCTRL_TIMEOUT: float = 2.0        # Seconds to wait for wmctrl output
_MIN_SCREEN_DIM: int = 100          # Minimum sane screen dimension


def get_windows(sw: int, sh: int) -> list[tuple[int, int, int, int]]:
    """Query wmctrl for visible, reasonably-sized non-fullscreen windows.
    
    Returns list of (x, y, width, height) tuples for candidate windows.
    Backwards compatible: returns empty list if wmctrl unavailable or fails.
    """
    global _wmctrl_available

    # Validate screen dimensions
    if sw < _MIN_SCREEN_DIM or sh < _MIN_SCREEN_DIM:
        log.debug("Screen dimensions %dx%d too small, skipping window query", sw, sh)
        return []

    # Thread-safe lazy initialization
    if _wmctrl_available is None:
        with _wmctrl_lock:
            # Double-check after acquiring lock
            if _wmctrl_available is None:
                _wmctrl_available = shutil.which("wmctrl") is not None
                if not _wmctrl_available:
                    log.info(
                        "wmctrl not found — window-top perching is disabled. "
                        "Install with: sudo apt install wmctrl"
                    )
                elif os.getenv("XDG_SESSION_TYPE") == "wayland":
                    log.info(
                        "Wayland session detected — wmctrl may have limited functionality. "
                        "Window-top perching might not work as expected."
                    )

    if not _wmctrl_available:
        return []

    try:
        raw = subprocess.check_output(
            ["wmctrl", "-l", "-G"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_WMCTRL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.warning("wmctrl timed out after %.1fs", _WMCTRL_TIMEOUT)
        return []
    except subprocess.CalledProcessError as e:
        log.debug("wmctrl exited with code %d", e.returncode)
        return []
    except OSError as e:
        log.debug("wmctrl failed: %s", e)
        return []

    wins: list[tuple[int, int, int, int]] = []
    for line in raw.splitlines():
        parts = line.split(None, 6)  # Split on whitespace, max 7 fields
        if len(parts) < 6:
            log.debug("Skipping malformed wmctrl line: %r", line)
            continue
        
        try:
            # parts[0] = window id, parts[1] = desktop (-1 = sticky/all desktops)
            desktop = int(parts[1])
            if desktop < 0:
                continue  # Skip sticky windows (panels, docks, etc.)
            
            x, y, w, h = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
        except (ValueError, IndexError) as e:
            log.debug("Failed to parse wmctrl line %r: %s", line, e)
            continue

        # Filter by size constraints
        if w < _MIN_WINDOW_SIZE or h < _MIN_WINDOW_SIZE:
            continue
        if w >= sw - _FULLSCREEN_MARGIN and h >= sh - _FULLSCREEN_MARGIN:
            continue  # Skip fullscreen or near-fullscreen windows
        
        wins.append((x, y, w, h))
    
    return wins


def reset_wmctrl_cache() -> None:
    """Force re-detection of wmctrl availability on next call.
    
    Useful if wmctrl was installed/uninstalled during runtime.
    """
    global _wmctrl_available
    with _wmctrl_lock:
        _wmctrl_available = None
