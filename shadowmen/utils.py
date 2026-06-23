import threading
import shutil
import subprocess
import os
import sys
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any, Dict

log = logging.getLogger(__name__)

# Module-level lock for thread-safe initialization
_wm_lock = threading.Lock()
_wm_available: bool | None = None
_MIN_WINDOW_SIZE: int = 80          # Minimum width/height to be "reasonably-sized"
_FULLSCREEN_MARGIN: int = 10        # Pixels of tolerance for fullscreen detection
_WM_TIMEOUT: float = 2.0        # Seconds to wait for wm output
_MIN_SCREEN_DIM: int = 100          # Minimum sane screen dimension

@dataclass(frozen=True)
class WindowSnapshot:
    """Immutable snapshot of window geometry to prevent race conditions."""
    x: int
    y: int
    w: int
    h: int
    id: str
    biome: str = "neutral"

class SpatialHash:
    """A simple grid-based spatial hash for O(1) neighbor lookups."""
    def __init__(self, cell_size: int = 120):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], List[Any]] = {}

    def insert(self, obj: Any, x: float, y: float) -> None:
        key = (int(x // self.cell_size), int(y // self.cell_size))
        if key not in self.grid:
            self.grid[key] = []
        self.grid[key].append(obj)

    def query(self, x: float, y: float, radius: float) -> List[Any]:
        results = []
        x_start = int((x - radius) // self.cell_size)
        x_end = int((x + radius) // self.cell_size)
        y_start = int((y - radius) // self.cell_size)
        y_end = int((y + radius) // self.cell_size)

        for gx in range(x_start, x_end + 1):
            for gy in range(y_start, y_end + 1):
                objs = self.grid.get((gx, gy))
                if objs:
                    results.extend(objs)
        return results

def get_windows(sw: int, sh: int) -> List[WindowSnapshot]:
    """Query OS for visible, reasonably-sized non-fullscreen windows."""
    if sw < _MIN_SCREEN_DIM or sh < _MIN_SCREEN_DIM:
        return []

    if sys.platform == "win32":
        return _get_windows_win32(sw, sh)
    elif sys.platform == "darwin":
        return _get_windows_darwin(sw, sh)
    else:
        return _get_windows_linux(sw, sh)

def _get_windows_linux(sw: int, sh: int) -> List[WindowSnapshot]:
    global _wm_available
    if _wm_available is None:
        with _wm_lock:
            if _wm_available is None:
                _wm_available = shutil.which("wmctrl") is not None
                if not _wm_available:
                    log.info("wmctrl not found — window-top perching disabled.")
                elif os.getenv("XDG_SESSION_TYPE") == "wayland":
                    log.info("Wayland session detected — wmctrl functionality may be limited.")

    if not _wm_available:
        return []

    try:
        raw = subprocess.check_output(
            ["wmctrl", "-l", "-G"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_WM_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return []

    wins: List[WindowSnapshot] = []
    for line in raw.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 6: continue
        try:
            wid = parts[0]
            desktop = int(parts[1])
            if desktop < 0: continue
            x, y, w, h = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
            title = parts[6].lower() if len(parts) > 6 else ""
            if w < _MIN_WINDOW_SIZE or h < _MIN_WINDOW_SIZE: continue
            if w >= sw - _FULLSCREEN_MARGIN and h >= sh - _FULLSCREEN_MARGIN: continue

            biome = "neutral"
            if "terminal" in title or "term" in title: biome = "hardened"
            elif "browser" in title or "firefox" in title or "chrome" in title: biome = "information-rich"
            wins.append(WindowSnapshot(x, y, w, h, wid, biome))
        except (ValueError, IndexError): continue
    return wins

def _get_windows_win32(sw: int, sh: int) -> List[WindowSnapshot]:
    try:
        import pygetwindow as gw
        wins: List[WindowSnapshot] = []
        for w in gw.getAllWindows():
            if not w.visible or w.isMinimized or w.title == "": continue
            if w.width < _MIN_WINDOW_SIZE or w.height < _MIN_WINDOW_SIZE: continue
            if w.width >= sw - _FULLSCREEN_MARGIN and w.height >= sh - _FULLSCREEN_MARGIN: continue

            title = w.title.lower()
            biome = "neutral"
            if "terminal" in title or "cmd" in title or "powershell" in title: biome = "hardened"
            elif "browser" in title or "firefox" in title or "chrome" in title: biome = "information-rich"

            wins.append(WindowSnapshot(w.left, w.top, w.width, w.height, str(w._hWnd), biome))
        return wins
    except ImportError:
        return []

def _get_windows_darwin(sw: int, sh: int) -> List[WindowSnapshot]:
    # Placeholder for macOS using Quartz. Requires pyobjc-framework-Quartz
    try:
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        wins: List[WindowSnapshot] = []
        for w in window_list:
            # Bounds are in a dict
            bounds = w.get('kCGWindowBounds', {})
            x, y, width, height = bounds.get('X', 0), bounds.get('Y', 0), bounds.get('Width', 0), bounds.get('Height', 0)
            if width < _MIN_WINDOW_SIZE or height < _MIN_WINDOW_SIZE: continue
            if width >= sw - _FULLSCREEN_MARGIN and height >= sh - _FULLSCREEN_MARGIN: continue

            wid = str(w.get('kCGWindowNumber', '0'))
            title = w.get('kCGWindowName', '').lower()
            biome = "neutral"
            if "terminal" in title or "iterm" in title: biome = "hardened"
            elif "browser" in title or "safari" in title or "chrome" in title: biome = "information-rich"

            wins.append(WindowSnapshot(int(x), int(y), int(width), int(height), wid, biome))
        return wins
    except ImportError:
        return []

def reset_wm_cache() -> None:
    global _wm_available
    with _wm_lock:
        _wm_available = None
