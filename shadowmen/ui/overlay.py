from __future__ import annotations

import logging
import math

from shadowmen.config import SimConfig
from shadowmen.entities import Colony
from shadowmen.ui.panel import ConfigPanel
from shadowmen.utils import get_windows, WindowSnapshot

try:
    import gi

    gi.require_version("Gtk", "3.0")
    import cairo
    from gi.repository import Gdk, GLib, Gtk
except ImportError:
    pass

log = logging.getLogger(__name__)


class ShadowMen(Gtk.Window):
    """Fullscreen transparent GTK overlay window that hosts the simulation."""

    def __init__(self, config: SimConfig) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.config = config

        scr = self.get_screen()
        disp = Gdk.Display.get_default()
        mon = disp.get_primary_monitor() or disp.get_monitor(0)
        geo = mon.get_geometry()
        self.sw, self.sh = geo.width, geo.height

        visual = scr.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        else:
            log.warning("No RGBA visual — overlay will be opaque.")

        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.resize(self.sw, self.sh)
        self.move(0, 0)
        try:
            self.input_shape_combine_region(cairo.Region())  # type: ignore
        except Exception as e:
            log.warning("Failed to make window input-transparent: %s", e)

        area = Gtk.DrawingArea()
        area.connect("draw", self._on_draw)
        self.add(area)
        self.area = area

        self.colony: Colony = Colony(config.population, self.sw, self.sh, config=config)
        self.win_cache: list[WindowSnapshot] = []
        self._win_tick: int = 0
        self._panel: ConfigPanel | None = None

        self._setup_tray_icon()

        GLib.timeout_add(33, self._tick)
        self.show_all()

    def _setup_tray_icon(self) -> None:
        try:
            icon = Gtk.StatusIcon()
            icon.set_from_icon_name("preferences-system")
            icon.set_tooltip_text("Shadow Men — click to configure")
            icon.connect("activate", lambda _: self.open_config_panel())
            self._tray_icon = icon
        except Exception as e:
            log.warning("Failed to initialize tray icon: %s", e)
            self._tray_icon = None

    def open_config_panel(self) -> None:
        if self._panel is not None:
            self._panel.present()
            return

        def _on_apply(cfg: SimConfig, restart: bool) -> None:
            if restart:
                self.colony.save()
                self.colony = Colony(cfg.population, self.sw, self.sh, config=cfg)
            else:
                if cfg.use_predator and not self.colony.predator:
                    from shadowmen.entities import Predator

                    self.colony.predator = Predator(self.sw, self.sh, cfg)
                elif not cfg.use_predator:
                    self.colony.predator = None

        def _on_reset_generations() -> None:
            # SAVE_FILE has already been removed by the panel; rebuild from scratch.
            self.colony = Colony(self.config.population, self.sw, self.sh, config=self.config)

        self._panel = ConfigPanel(
            self.config, on_apply=_on_apply, on_reset_generations=_on_reset_generations
        )
        self._panel.connect("destroy", self._on_panel_destroy)

    def _on_panel_destroy(self, _win: Gtk.Window) -> None:
        self._panel = None

    def _tick(self) -> bool:
        self._win_tick += 1
        if self._win_tick >= 15:
            old = self.win_cache
            self.win_cache = get_windows(self.sw, self.sh)
            self._win_tick = 0

            if len(old) != len(self.win_cache) or any(
                abs(o.x - n.x) > 5 or abs(o.y - n.y) > 5
                for o, n in zip(sorted(old, key=lambda w: w.id), sorted(self.win_cache, key=lambda w: w.id))
            ):
                self.colony.react_to_windows(old, self.win_cache)

        self.colony.tick(self.win_cache)
        self.area.queue_draw()
        return True

    def _on_draw(self, _widget: Gtk.Widget, cr: cairo.Context) -> bool:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        for p in self.colony.people:
            p.draw(cr)

        self._draw_kill_effects(cr)

        if self.colony.predator:
            self.colony.predator.draw(cr)

        if not self.colony.people:
            self._draw_extinction_overlay(cr)

        self._draw_stats_hud(cr)
        return False

    def _draw_kill_effects(self, cr: cairo.Context) -> None:
        for ke in self.colony.kill_effects:
            if ke.max_age <= 0: continue
            ratio = ke.age / ke.max_age
            alpha = 0.75 * (1.0 - ratio)
            radius = 8 + ratio * 22

            # Glow effect
            cr.set_source_rgba(0.95, 0.2, 0.1, alpha * 0.3)
            cr.arc(ke.x, ke.y, radius * 1.5, 0, 2 * math.pi)
            cr.fill()

            cr.set_source_rgba(0.95, 0.06, 0.02, alpha)
            cr.arc(ke.x, ke.y, radius, 0, 2 * math.pi)
            cr.fill()

    def _draw_extinction_overlay(self, cr: cairo.Context) -> None:
        msg = "COLONY EXTINCT"
        sub = "run with --reset to start fresh"

        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)

        # Draw main message
        cr.set_font_size(32)
        ext = cr.text_extents(msg)
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.move_to(self.sw / 2 - ext.width / 2 + 2, self.sh / 2 + 2)
        cr.show_text(msg)
        cr.set_source_rgba(0.9, 0.1, 0.1, 0.8)
        cr.move_to(self.sw / 2 - ext.width / 2, self.sh / 2)
        cr.show_text(msg)

        # Draw sub message
        cr.set_font_size(14)
        ext = cr.text_extents(sub)
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.move_to(self.sw / 2 - ext.width / 2 + 1, self.sh / 2 + 30 + 1)
        cr.show_text(sub)
        cr.set_source_rgba(0.8, 0.8, 0.8, 0.7)
        cr.move_to(self.sw / 2 - ext.width / 2, self.sh / 2 + 30)
        cr.show_text(sub)

    def _draw_stats_hud(self, cr: cairo.Context) -> None:
        stats = self.colony.stats()
        if not stats:
            return
        cr.set_font_size(11)
        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

        # Subtle background for stats
        cr.set_source_rgba(0, 0, 0, 0.25)
        cr.rectangle(5, self.sh - 25, 300, 20)
        cr.fill()

        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.move_to(11, self.sh - 9)
        cr.show_text(stats)
        cr.set_source_rgba(1, 1, 0.8, 0.7)
        cr.move_to(10, self.sh - 10)
        cr.show_text(stats)
