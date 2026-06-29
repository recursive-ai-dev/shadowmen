from __future__ import annotations
from typing import Any

import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def _get_platform_paths() -> tuple[Path, Path, Path | None]:
    """Determine OS-specific paths for config, data, and autostart files."""
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            appdata = str(home / "AppData/Roaming")
        localappdata = os.getenv("LOCALAPPDATA")
        if not localappdata:
            localappdata = str(home / "AppData/Local")

        config = Path(appdata) / "shadowmen"
        data = Path(localappdata) / "shadowmen"
        autostart = None
    elif sys.platform == "darwin":
        config = home / "Library/Application Support/shadowmen"
        data = config
        autostart = None
    else:
        # Linux / XDG defaults
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if not xdg_config:
            xdg_config = str(home / ".config")
        xdg_data = os.getenv("XDG_DATA_HOME")
        if not xdg_data:
            xdg_data = str(home / ".local/share")

        config_root = Path(xdg_config)
        data_root = Path(xdg_data)
        config = config_root / "shadowmen"
        data = data_root / "shadowmen"
        autostart = config_root / "autostart" / "shadowmen.desktop"

    return config, data, autostart


CONFIG_DIR, DATA_DIR, AUTOSTART_FILE = _get_platform_paths()
CONFIG_FILE = CONFIG_DIR / "config.json"
SAVE_FILE = DATA_DIR / "population.json"
LOCK_FILE = DATA_DIR / "shadowmen.lock"

LEGACY_CONFIG = Path.home() / ".shadowmen_config.json"
LEGACY_SAVE = Path.home() / ".shadowmen_pop.json"


def migrate_legacy_files() -> None:
    """Migrate configuration and population files from legacy locations to platform-standard directories."""
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


_lock_handle: Any = None


def acquire_single_instance_lock(path: Path = LOCK_FILE) -> bool:
    """Attempt to acquire a file lock to ensure only one instance of the application is running."""
    global _lock_handle
    if _lock_handle is not None:
        return True

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError as e:
        log.warning(
            "Could not open lock file %s (%s); skipping single-instance guard.", path, e
        )
        return True

    if sys.platform == "win32":
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (ImportError, OSError):
            handle.close()
            return False
    else:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, BlockingIOError, OSError):
            handle.close()
            return False

    try:
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        _lock_handle = handle
        return True
    except OSError as e:
        log.warning("Failed to write to lock file: %s", e)
        handle.close()
        return False


def release_single_instance_lock() -> None:
    """Release the previously acquired single instance lock."""
    global _lock_handle
    if _lock_handle is not None:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
            _lock_handle.close()
        except Exception as e:
            log.warning("Failed to release lock cleanly: %s", e)
        finally:
            _lock_handle = None
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except OSError:
                pass


@dataclass
class SimConfig:
    """Global simulation parameters and configuration settings."""

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
        return max(1, int(self.evolve_base_ticks / max(0.001, self.evo_speed)))

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
        if not isinstance(d, dict):
            return defs

        def _get_int(key: str, default: int) -> int:
            val = d.get(key)
            if val is None:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _get_float(key: str, default: float) -> float:
            val = d.get(key)
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def _get_bool(key: str, default: bool) -> bool:
            val = d.get(key)
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            try:
                return bool(val)
            except (ValueError, TypeError):
                return default

        return cls(
            population=_get_int("population", defs.population),
            evo_speed=_get_float("evo_speed", defs.evo_speed),
            evolve_base_ticks=_get_int("evolve_base_ticks", defs.evolve_base_ticks),
            use_predator=_get_bool("use_predator", defs.use_predator),
            pred_base_speed=_get_float("pred_base_speed", defs.pred_base_speed),
            pred_speed_inc=_get_float("pred_speed_inc", defs.pred_speed_inc),
            pred_speed_cap=_get_float("pred_speed_cap", defs.pred_speed_cap),
            flee_radius_x=_get_int("flee_radius_x", defs.flee_radius_x),
            flee_radius_y=_get_int("flee_radius_y", defs.flee_radius_y),
            panic_radius=_get_int("panic_radius", defs.panic_radius),
            kill_effect_ticks=_get_int("kill_effect_ticks", defs.kill_effect_ticks),
        )

    def update_from(self, other: SimConfig) -> None:
        """Update this configuration with values from another SimConfig instance."""
        for key, val in other.to_dict().items():
            setattr(self, key, val)

    def clamp_fields(self) -> None:
        """Ensure all configuration values are within their allowed ranges."""

        def _ci(name: str, lo: int, hi: int = 1_000_000) -> None:
            v = getattr(self, name)
            c = max(lo, min(hi, v))
            if c != v:
                setattr(self, name, c)

        def _cf(name: str, lo: float, hi: float = 1e9) -> None:
            v = getattr(self, name)
            c = max(lo, min(hi, v))
            if c != v:
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
        """Validate configuration settings and return a list of error messages."""
        errors: list[str] = []
        if self.population < 1:
            errors.append("population must be ≥ 1")
        return errors


def load_config(path: Path = CONFIG_FILE) -> SimConfig:
    """Load simulation configuration from a JSON file."""
    if path.exists():
        try:
            cfg = SimConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
            cfg.clamp_fields()
            return cfg
        except json.JSONDecodeError as e:
            log.error("Failed to parse config JSON in %s: %s", path, e)
        except OSError as e:
            log.error("Failed to read config file %s: %s", path, e)
        except Exception as e:
            log.error("Unexpected error loading config from %s: %s", path, e)
    return SimConfig()


def save_config(cfg: SimConfig, path: Path = CONFIG_FILE) -> None:
    """Save simulation configuration to a JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    except OSError as e:
        log.error("Failed to save config to %s: %s", path, e)
