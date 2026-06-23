import threading
import shutil
import subprocess
import os
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any, Dict

log = logging.getLogger(__name__)

# Module-level lock for thread-safe initialization
_wmctrl_lock = threading.Lock()
_wmctrl_available: bool | None = None
_MIN_WINDOW_SIZE: int = 80          # Minimum width/height to be "reasonably-sized"
_FULLSCREEN_MARGIN: int = 10        # Pixels of tolerance for fullscreen detection
_WMCTRL_TIMEOUT: float = 2.0        # Seconds to wait for wmctrl output
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
    """Query wmctrl for visible, reasonably-sized non-fullscreen windows."""
    global _wmctrl_available

    if sw < _MIN_SCREEN_DIM or sh < _MIN_SCREEN_DIM:
        return []

    if _wmctrl_available is None:
        with _wmctrl_lock:
            if _wmctrl_available is None:
                _wmctrl_available = shutil.which("wmctrl") is not None
                if not _wmctrl_available:
                    log.info("wmctrl not found — window-top perching disabled.")
                elif os.getenv("XDG_SESSION_TYPE") == "wayland":
                    log.info("Wayland session detected — wmctrl functionality may be limited.")

    if not _wmctrl_available:
        return []

    try:
        raw = subprocess.check_output(
            ["wmctrl", "-l", "-G"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_WMCTRL_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return []

    wins: List[WindowSnapshot] = []
    for line in raw.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        
        try:
            wid = parts[0]
            desktop = int(parts[1])
            if desktop < 0: continue
            
            x, y, w, h = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
            title = parts[6].lower() if len(parts) > 6 else ""
        except (ValueError, IndexError):
            continue

        if w < _MIN_WINDOW_SIZE or h < _MIN_WINDOW_SIZE:
            continue
        if w >= sw - _FULLSCREEN_MARGIN and h >= sh - _FULLSCREEN_MARGIN:
            continue
        
        # Biome detection
        biome = "neutral"
        if "terminal" in title or "term" in title:
            biome = "hardened"
        elif "browser" in title or "firefox" in title or "chrome" in title:
            biome = "information-rich"

        wins.append(WindowSnapshot(x, y, w, h, wid, biome))
    
    return wins

def reset_wmctrl_cache() -> None:
    global _wmctrl_available
    with _wmctrl_lock:
        _wmctrl_available = None
