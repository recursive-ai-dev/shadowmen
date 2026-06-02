from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def _get_xdg_path(env_var: str, default_rel: Path) -> Path:
    val = os.getenv(env_var)
    if val:
        return Path(val)
    return Path.home() / default_rel


CONFIG_DIR = _get_xdg_path("XDG_CONFIG_HOME", Path(".config")) / "shadowmen"
DATA_DIR = _get_xdg_path("XDG_DATA_HOME", Path(".local/share")) / "shadowmen"

CONFIG_FILE = CONFIG_DIR / "config.json"
SAVE_FILE = DATA_DIR / "population.json"
LOCK_FILE = DATA_DIR / "shadowmen.lock"
AUTOSTART_FILE = (
    _get_xdg_path("XDG_CONFIG_HOME", Path(".config")) / "autostart" / "shadowmen.desktop"
)

LEGACY_CONFIG = Path.home() / ".shadowmen_config.json"
LEGACY_SAVE = Path.home() / ".shadowmen_pop.json"


def migrate_legacy_files() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if LEGACY_CONFIG.exists() and not CONFIG_FILE.exists():
        try:
            shutil.move(str(LEGACY_CONFIG), str(CONFIG_FILE))
            log.info("Migrated config: %s -> %s", LEGACY_CONFIG, CONFIG_FILE)
        except OSError as e:
            log.warning("Failed to migrate config: %s", e)

    if LEGACY_SAVE.exists() and not SAVE_FILE.exists():
        try:
            shutil.move(str(LEGACY_SAVE), str(SAVE_FILE))
            log.info("Migrated population: %s -> %s", LEGACY_SAVE, SAVE_FILE)
        except OSError as e:
            log.warning("Failed to migrate population: %s", e)


# Held open for the lifetime of the process to keep the single-instance lock.
# The kernel drops the flock when this fd is closed or the process exits.
_lock_handle: object | None = None


def acquire_single_instance_lock(path: Path = LOCK_FILE) -> bool:
    """Take an exclusive, non-blocking lock so only one instance can run.

    Returns ``True`` if this process now holds the lock (or already did), and
    ``False`` if another live instance is holding it. The lock is an advisory
    ``flock`` on an open file descriptor stored at module scope; the OS releases
    it automatically when the process exits — even on a crash — so no stale lock
    file is ever left behind to clean up.
    """
    global _lock_handle
    if _lock_handle is not None:
        return True  # already locked by this process; idempotent
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode so a rival instance's pid text is not truncated before we
        # know whether we actually won the lock.
        handle = path.open("a+")
    except OSError as e:
        log.warning("Could not open lock file %s (%s); skipping single-instance guard.", path, e)
        return True
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return False
    except OSError as e:
        # e.g. filesystem without flock support — fail open rather than block startup.
        log.warning("flock unavailable on %s (%s); skipping single-instance guard.", path, e)
        handle.close()
        return True
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    _lock_handle = handle
    return True


@dataclass
class SimConfig:
    """All user-editable simulation parameters."""

    population: int = 8
    evo_speed: float = 1.0
    evolve_base_ticks: int = 600
    use_predator: bool = False
    pred_base_speed: float = 6.2
    pred_speed_inc: float = 0.22
    pred_speed_cap: float = 13.0
    flee_radius_x: int = 200
    flee_radius_y: int = 55
    panic_radius: int = 130
    kill_effect_ticks: int = 48

    @property
    def evolve_every(self) -> int:
        return max(1, int(self.evolve_base_ticks / self.evo_speed))

    def to_dict(self) -> dict:
        return {
            "population": self.population,
            "evo_speed": self.evo_speed,
            "evolve_base_ticks": self.evolve_base_ticks,
            "use_predator": self.use_predator,
            "pred_base_speed": self.pred_base_speed,
            "pred_speed_inc": self.pred_speed_inc,
            "pred_speed_cap": self.pred_speed_cap,
            "flee_radius_x": self.flee_radius_x,
            "flee_radius_y": self.flee_radius_y,
            "panic_radius": self.panic_radius,
            "kill_effect_ticks": self.kill_effect_ticks,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SimConfig:
        defs = cls()
        return cls(
            population=int(d.get("population", defs.population)),
            evo_speed=float(d.get("evo_speed", defs.evo_speed)),
            evolve_base_ticks=int(d.get("evolve_base_ticks", defs.evolve_base_ticks)),
            use_predator=bool(d.get("use_predator", defs.use_predator)),
            pred_base_speed=float(d.get("pred_base_speed", defs.pred_base_speed)),
            pred_speed_inc=float(d.get("pred_speed_inc", defs.pred_speed_inc)),
            pred_speed_cap=float(d.get("pred_speed_cap", defs.pred_speed_cap)),
            flee_radius_x=int(d.get("flee_radius_x", defs.flee_radius_x)),
            flee_radius_y=int(d.get("flee_radius_y", defs.flee_radius_y)),
            panic_radius=int(d.get("panic_radius", defs.panic_radius)),
            kill_effect_ticks=int(d.get("kill_effect_ticks", defs.kill_effect_ticks)),
        )

    def update_from(self, other: SimConfig) -> None:
        for key, val in other.to_dict().items():
            setattr(self, key, val)

    def clamp_fields(self) -> None:
        def _ci(name: str, lo: int, hi: int = 1_000_000) -> None:
            v = getattr(self, name)
            c = max(lo, min(hi, v))
            if c != v:
                log.warning(
                    "Config: %s=%d out of range [%d, %d]; clamped to %d.", name, v, lo, hi, c
                )
                setattr(self, name, c)

        def _cf(name: str, lo: float, hi: float = 1e9) -> None:
            v = getattr(self, name)
            c = max(lo, min(hi, v))
            if c != v:
                log.warning(
                    "Config: %s=%g out of range [%g, %g]; clamped to %g.", name, v, lo, hi, c
                )
                setattr(self, name, c)

        _ci("population", lo=1, hi=500)
        _cf("evo_speed", lo=0.01, hi=100.0)
        _ci("evolve_base_ticks", lo=1, hi=108_000)
        _cf("pred_base_speed", lo=0.1, hi=50.0)
        _cf("pred_speed_inc", lo=0.0, hi=10.0)
        _cf("pred_speed_cap", lo=0.1, hi=50.0)
        _ci("flee_radius_x", lo=1, hi=5_000)
        _ci("flee_radius_y", lo=1, hi=2_000)
        _ci("panic_radius", lo=1, hi=5_000)
        _ci("kill_effect_ticks", lo=1, hi=600)

        if self.pred_speed_cap < self.pred_base_speed:
            self.pred_speed_cap = self.pred_base_speed

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.population < 1:
            errors.append(f"population must be ≥ 1, got {self.population}")
        if self.evo_speed <= 0:
            errors.append(f"evo_speed must be > 0, got {self.evo_speed}")
        if self.evolve_base_ticks < 1:
            errors.append(f"evolve_base_ticks must be ≥ 1, got {self.evolve_base_ticks}")
        if self.pred_base_speed <= 0:
            errors.append(f"pred_base_speed must be > 0, got {self.pred_base_speed}")
        if self.pred_speed_inc < 0:
            errors.append(f"pred_speed_inc must be ≥ 0, got {self.pred_speed_inc}")
        if self.pred_speed_cap <= 0:
            errors.append(f"pred_speed_cap must be > 0, got {self.pred_speed_cap}")
        if self.pred_speed_cap < self.pred_base_speed:
            errors.append(
                f"pred_speed_cap ({self.pred_speed_cap}) must be ≥ "
                f"pred_base_speed ({self.pred_base_speed})"
            )
        return errors


def load_config(path: Path = CONFIG_FILE) -> SimConfig:
    if path.exists():
        try:
            cfg = SimConfig.from_dict(json.loads(path.read_text()))
            cfg.clamp_fields()
            return cfg
        except Exception as e:
            log.warning("Config file unreadable (%s); using defaults.", e)
    return SimConfig()


def save_config(cfg: SimConfig, path: Path = CONFIG_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg.to_dict(), indent=2))
        log.info("Config saved → %s", path)
    except OSError as e:
        log.error("Failed to save config to %s: %s", path, e)
