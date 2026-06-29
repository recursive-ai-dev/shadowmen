from __future__ import annotations

import argparse
import logging
import os
import signal
import sys


def check_dependencies() -> None:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
    except ImportError:
        if sys.platform == "win32":
            msg = "Install: MSYS2/MinGW-w64 or Gtk-for-Windows-Runtime"
        elif sys.platform == "darwin":
            msg = "Install: brew install pygobject3 gtk+3"
        else:
            msg = "Install: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
        sys.exit(f"GTK 3 not found. {msg}")


import contextlib

from shadowmen import __version__
from shadowmen.config import (
    SAVE_FILE,
    SimConfig,
    acquire_single_instance_lock,
    load_config,
    migrate_legacy_files,
    release_single_instance_lock,
    save_config,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    check_dependencies()
    from gi.repository import GLib, Gtk

    from shadowmen.ui.overlay import ShadowMen
    from shadowmen.ui.panel import ConfigPanel, install_autostart

    migrate_legacy_files()

    ap = argparse.ArgumentParser(description="Evolving shadow people")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--count", type=int, help="population size")
    ap.add_argument("--predator", action="store_true", help="enable predator")
    ap.add_argument("--evo-speed", type=float, help="evolution speed multiplier")
    ap.add_argument("--evolve-every", type=int, help="evolve base ticks")
    ap.add_argument("--flee-radius-x", type=int, help="flee radius x")
    ap.add_argument("--flee-radius-y", type=int, help="flee radius y")
    ap.add_argument("--panic-radius", type=int, help="panic radius")
    ap.add_argument("--pred-base-speed", type=float, help="predator base speed")
    ap.add_argument("--pred-speed-inc", type=float, help="predator speed per kill")
    ap.add_argument("--pred-speed-cap", type=float, help="predator speed cap")
    ap.add_argument("--kill-effect-ticks", type=int, help="kill effect frames")
    ap.add_argument("--config-panel", action="store_true", help="open config panel")
    ap.add_argument("--reset", action="store_true", help="wipe population")
    ap.add_argument("--install-autostart", action="store_true")
    args = ap.parse_args()

    if sys.platform not in ("win32", "darwin"):
        if (
            not os.environ.get("DISPLAY")
            and not os.environ.get("WAYLAND_DISPLAY")
            and not args.install_autostart
        ):
            sys.exit(
                "No display detected. Run this on a desktop session with a display server."
            )

    cfg = load_config()

    if args.count:
        cfg.population = args.count
    if args.predator:
        cfg.use_predator = True
    if args.evo_speed:
        cfg.evo_speed = args.evo_speed
    if args.evolve_every:
        cfg.evolve_base_ticks = args.evolve_every
    if args.flee_radius_x:
        cfg.flee_radius_x = args.flee_radius_x
    if args.flee_radius_y:
        cfg.flee_radius_y = args.flee_radius_y
    if args.panic_radius:
        cfg.panic_radius = args.panic_radius
    if args.pred_base_speed:
        cfg.pred_base_speed = args.pred_base_speed
    if args.pred_speed_inc:
        cfg.pred_speed_inc = args.pred_speed_inc
    if args.pred_speed_cap:
        cfg.pred_speed_cap = args.pred_speed_cap
    if args.kill_effect_ticks:
        cfg.kill_effect_ticks = args.kill_effect_ticks

    if args.install_autostart:
        install_autostart(cfg)
        sys.exit(0)

    if args.reset:
        try:
            if SAVE_FILE.exists():
                SAVE_FILE.unlink()
            log.info("Population reset.")
        except OSError as e:
            log.warning("Failed to reset population file: %s", e)

    if args.config_panel:

        def _on_apply(c: SimConfig, restart: bool) -> None:
            save_config(c)
            if not restart:
                log.info("Settings applied.")

        panel = ConfigPanel(cfg, on_apply=_on_apply)
        panel.connect("destroy", Gtk.main_quit)
        with contextlib.suppress(KeyboardInterrupt):
            Gtk.main()
        sys.exit(0)

    if not acquire_single_instance_lock():
        sys.exit("Shadow Men is already running — only one instance can run at a time.")

    try:
        app = ShadowMen(cfg)

        def _quit(*_: object) -> None:
            app.colony.save()
            Gtk.main_quit()

        if sys.platform != "win32":
            signal.signal(signal.SIGINT, _quit)
            signal.signal(signal.SIGTERM, _quit)

        GLib.timeout_add(200, lambda: True)

        try:
            Gtk.main()
        except KeyboardInterrupt:
            _quit()
    finally:
        release_single_instance_lock()


if __name__ == "__main__":
    main()
