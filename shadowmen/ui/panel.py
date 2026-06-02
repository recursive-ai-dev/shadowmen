from __future__ import annotations

import copy
import logging
import shlex
from collections.abc import Callable

from shadowmen.config import AUTOSTART_FILE, SAVE_FILE, SimConfig, save_config

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk
except ImportError:
    pass

log = logging.getLogger(__name__)


def _autostart_args(cfg: SimConfig) -> str:
    parts: list[str] = []
    defs = SimConfig()
    if cfg.population != defs.population:
        parts.append(f"--count {cfg.population}")
    if cfg.use_predator:
        parts.append("--predator")
    if cfg.evo_speed != defs.evo_speed:
        parts.append(f"--evo-speed {shlex.quote(f'{cfg.evo_speed:.2f}')}")
    if cfg.evolve_base_ticks != defs.evolve_base_ticks:
        parts.append(f"--evolve-every {cfg.evolve_base_ticks}")
    if cfg.flee_radius_x != defs.flee_radius_x:
        parts.append(f"--flee-radius-x {cfg.flee_radius_x}")
    if cfg.flee_radius_y != defs.flee_radius_y:
        parts.append(f"--flee-radius-y {cfg.flee_radius_y}")
    if cfg.panic_radius != defs.panic_radius:
        parts.append(f"--panic-radius {cfg.panic_radius}")
    if cfg.pred_base_speed != defs.pred_base_speed:
        parts.append(f"--pred-base-speed {shlex.quote(f'{cfg.pred_base_speed:.2f}')}")
    if cfg.pred_speed_inc != defs.pred_speed_inc:
        parts.append(f"--pred-speed-inc {shlex.quote(f'{cfg.pred_speed_inc:.2f}')}")
    if cfg.pred_speed_cap != defs.pred_speed_cap:
        parts.append(f"--pred-speed-cap {shlex.quote(f'{cfg.pred_speed_cap:.2f}')}")
    if cfg.kill_effect_ticks != defs.kill_effect_ticks:
        parts.append(f"--kill-effect-ticks {cfg.kill_effect_ticks}")
    return " ".join(parts)


def install_autostart(cfg: SimConfig) -> bool:
    try:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        args = _autostart_args(cfg)
        cmd = "shadowmen" + (f" {args}" if args else "")
        AUTOSTART_FILE.write_text(f"""[Desktop Entry]
Type=Application
Name=Shadow Men
Comment=Evolving shadow people desktop widget
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
""")
        log.info("Autostart installed → %s", AUTOSTART_FILE)
        return True
    except Exception as e:
        log.error("Failed to install autostart: %s", e)
        return False


class ConfigPanel(Gtk.Window):
    """Non-modal GTK window for visually editing all SimConfig parameters."""

    def __init__(
        self,
        cfg: SimConfig,
        *,
        on_apply: Callable[[SimConfig, bool], None] | None = None,
        on_reset_generations: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title="Shadow Men — Configuration")
        self._cfg = cfg
        self._working = copy.deepcopy(cfg)
        self._on_apply = on_apply
        self._on_reset_generations = on_reset_generations
        self._refreshing = False
        self._adjustments: dict[str, Gtk.Adjustment] = {}
        self._switches: dict[str, Gtk.Switch] = {}
        self._preview_lbl: Gtk.Label | None = None

        self.set_default_size(540, 520)
        self.set_resizable(False)
        self.set_border_width(0)

        self.connect("delete-event", self._on_delete_event)
        self._build_ui()
        self.show_all()

    def _build_ui(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        outer.pack_start(notebook, True, True, 0)

        tabs = [
            ("Colony", self._build_colony_tab),
            ("Predator", self._build_predator_tab),
            ("Flee & Panic", self._build_flee_tab),
            ("Visual", self._build_visual_tab),
            ("Autostart", self._build_autostart_tab),
        ]
        for title, builder in tabs:
            notebook.append_page(builder(), Gtk.Label(label=title))

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(sep, False, False, 0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_border_width(10)
        outer.pack_start(bar, False, False, 0)

        btn_reset = Gtk.Button(label="Reset to Defaults")
        btn_reset.connect("clicked", self._on_reset)
        bar.pack_start(btn_reset, False, False, 0)

        bar.pack_start(Gtk.Box(), True, True, 0)

        btn_restart = Gtk.Button(label="Apply & Restart")
        btn_restart.connect("clicked", lambda _: self._do_apply(restart=True))
        bar.pack_start(btn_restart, False, False, 0)

        btn_apply = Gtk.Button(label="Apply")
        btn_apply.get_style_context().add_class("suggested-action")
        btn_apply.connect("clicked", lambda _: self._do_apply(restart=False))
        bar.pack_start(btn_apply, False, False, 0)

        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda _: self.destroy())
        bar.pack_start(btn_close, False, False, 0)

        self._info_lbl = Gtk.Label(label="", xalign=0.0)
        self._info_lbl.set_margin_start(10)
        self._info_lbl.set_margin_bottom(6)
        outer.pack_start(self._info_lbl, False, False, 0)

    def _build_colony_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        box.pack_start(self._section_label("Colony"), False, False, 0)
        box.pack_start(
            self._int_row(
                "Population", "...", 1, 200, self._working.population, "population", True
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._float_row(
                "Evo Speed ×", "...", 0.25, 10.0, 0.25, 2, self._working.evo_speed, "evo_speed"
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._int_row(
                "Evo Base Ticks",
                "...",
                60,
                3600,
                self._working.evolve_base_ticks,
                "evolve_base_ticks",
            ),
            False,
            False,
            2,
        )

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 10)
        box.pack_start(self._section_label("Evolution History"), False, False, 0)
        desc = Gtk.Label(xalign=0.0)
        desc.set_line_wrap(True)
        desc.set_markup(
            '<span size="small" foreground="#999999">'
            "Wipe the saved population and start over at generation 0 "
            "with a fresh set of random genomes.</span>"
        )
        box.pack_start(desc, False, False, 0)

        reset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_reset_gens = Gtk.Button(label="Reset Generations")
        btn_reset_gens.get_style_context().add_class("destructive-action")
        btn_reset_gens.connect("clicked", self._on_reset_generations_clicked)
        reset_row.pack_start(btn_reset_gens, False, False, 0)
        box.pack_start(reset_row, False, False, 4)
        return box

    def _build_predator_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        box.pack_start(self._section_label("Predator"), False, False, 0)
        box.pack_start(
            self._bool_row(
                "Enable Predator", "...", self._working.use_predator, "use_predator", True
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._float_row(
                "Base Speed",
                "...",
                2.0,
                12.0,
                0.1,
                1,
                self._working.pred_base_speed,
                "pred_base_speed",
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._float_row(
                "Speed per Kill",
                "...",
                0.0,
                1.0,
                0.01,
                2,
                self._working.pred_speed_inc,
                "pred_speed_inc",
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._float_row(
                "Speed Cap",
                "...",
                5.0,
                20.0,
                0.5,
                1,
                self._working.pred_speed_cap,
                "pred_speed_cap",
            ),
            False,
            False,
            2,
        )
        return box

    def _build_flee_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        box.pack_start(self._section_label("Flee & Panic Behaviour"), False, False, 0)
        box.pack_start(
            self._int_row(
                "Flee Radius X (px)", "...", 50, 600, self._working.flee_radius_x, "flee_radius_x"
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._int_row(
                "Flee Radius Y (px)", "...", 10, 200, self._working.flee_radius_y, "flee_radius_y"
            ),
            False,
            False,
            2,
        )
        box.pack_start(
            self._int_row(
                "Panic Radius (px)", "...", 30, 500, self._working.panic_radius, "panic_radius"
            ),
            False,
            False,
            2,
        )
        return box

    def _build_visual_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        box.pack_start(self._section_label("Visual"), False, False, 0)
        box.pack_start(
            self._int_row(
                "Kill Effect Frames",
                "...",
                10,
                180,
                self._working.kill_effect_ticks,
                "kill_effect_ticks",
            ),
            False,
            False,
            2,
        )
        return box

    def _build_autostart_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        box.pack_start(self._section_label("Autostart"), False, False, 0)
        installed = AUTOSTART_FILE.exists()
        status_text = "Installed" if installed else "Not installed"
        self._autostart_status_lbl = Gtk.Label(xalign=0.0)
        self._autostart_status_lbl.set_markup(f"Status: <b>{status_text}</b>")
        box.pack_start(self._autostart_status_lbl, False, False, 0)

        self._preview_lbl = Gtk.Label(xalign=0.0)
        self._preview_lbl.set_selectable(True)
        self._preview_lbl.set_line_wrap(True)
        box.pack_start(self._preview_lbl, False, False, 10)
        self._refresh_autostart_preview()

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_install = Gtk.Button(label="Install Autostart")
        btn_install.connect("clicked", self._on_install_autostart)
        btn_row.pack_start(btn_install, False, False, 0)
        btn_uninstall = Gtk.Button(label="Uninstall")
        btn_uninstall.connect("clicked", self._on_uninstall_autostart)
        btn_row.pack_start(btn_uninstall, False, False, 0)
        box.pack_start(btn_row, False, False, 0)
        return box

    def _tab_box(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(16)
        return box

    def _section_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_margin_bottom(6)
        return lbl

    def _float_row(
        self,
        label: str,
        tooltip: str,
        lo: float,
        hi: float,
        step: float,
        digits: int,
        initial: float,
        field_name: str,
    ) -> Gtk.Widget:
        adj = Gtk.Adjustment(
            value=initial,
            lower=lo,
            upper=hi,
            step_increment=step,
            page_increment=step * 10,
            page_size=0,
        )
        self._adjustments[field_name] = adj
        adj.connect("value-changed", lambda a: self._set(field_name, round(a.get_value(), digits)))
        return self._scale_row(label, tooltip, adj, digits)

    def _int_row(
        self,
        label: str,
        tooltip: str,
        lo: int,
        hi: int,
        initial: int,
        field_name: str,
        restart_required: bool = False,
    ) -> Gtk.Widget:
        adj = Gtk.Adjustment(
            value=initial, lower=lo, upper=hi, step_increment=1, page_increment=10, page_size=0
        )
        self._adjustments[field_name] = adj
        adj.connect("value-changed", lambda a: self._set(field_name, int(a.get_value())))
        row = self._scale_row(label, tooltip, adj, digits=0)
        if restart_required:
            return self._wrap_restart_note(row)
        return row

    def _bool_row(
        self,
        label: str,
        tooltip: str,
        initial: bool,
        field_name: str,
        restart_required: bool = False,
    ) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_size_request(200, -1)
        sw = Gtk.Switch()
        sw.set_active(initial)
        self._switches[field_name] = sw
        sw.connect("notify::active", lambda w, _: self._set(field_name, w.get_active()))
        row.pack_start(lbl, False, False, 0)
        row.pack_start(sw, False, False, 0)
        if restart_required:
            note = Gtk.Label()
            note.set_markup(
                '  <span size="small" foreground="#999999"><i>⚠ restart required</i></span>'
            )
            row.pack_start(note, False, False, 0)
        return row

    def _scale_row(self, label: str, tooltip: str, adj: Gtk.Adjustment, digits: int) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_size_request(200, -1)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_hexpand(True)
        scale.set_draw_value(False)
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=adj.get_step_increment(), digits=digits)
        spin.set_size_request(90, -1)
        row.pack_start(lbl, False, False, 0)
        row.pack_start(scale, True, True, 0)
        row.pack_start(spin, False, False, 0)
        return row

    def _wrap_restart_note(self, row: Gtk.Widget) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.pack_start(row, False, False, 0)
        note = Gtk.Label()
        note.set_markup(
            '<span size="small" foreground="#999999"><i>  ⚠ restart required</i></span>'
        )
        note.set_xalign(0.0)
        note.set_margin_start(208)
        vbox.pack_start(note, False, False, 0)
        return vbox

    def _set(self, field_name: str, value: object) -> None:
        if not self._refreshing:
            setattr(self._working, field_name, value)
            self._refresh_autostart_preview()

    def _refresh_autostart_preview(self) -> None:
        if self._preview_lbl is None:
            return
        args = _autostart_args(self._working)
        cmd = "shadowmen" + (f" {args}" if args else "")
        self._preview_lbl.set_text(cmd)

    def _do_apply(self, restart: bool) -> None:
        self._cfg.update_from(self._working)
        save_config(self._cfg)
        if self._on_apply:
            self._on_apply(self._cfg, restart)

    def _on_reset(self, _btn: Gtk.Button) -> None:
        self._working = SimConfig()
        self._refreshing = True
        for name, adj in self._adjustments.items():
            adj.set_value(getattr(self._working, name))
        for name, sw in self._switches.items():
            sw.set_active(getattr(self._working, name))
        self._refreshing = False
        self._refresh_autostart_preview()

    def _on_reset_generations_clicked(self, _btn: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Reset all generations?",
        )
        dialog.format_secondary_text(
            "This permanently deletes the saved population. The colony will "
            "restart at generation 0. This cannot be undone."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return

        try:
            if SAVE_FILE.exists():
                SAVE_FILE.unlink()
            if self._on_reset_generations:
                self._on_reset_generations()
            self._info_lbl.set_markup(
                '<span foreground="#cc4444">Generations reset — colony restarted '
                "at generation 0.</span>"
            )
            log.info("Population reset via config panel.")
        except OSError as e:
            log.error("Failed to reset generations: %s", e)
            self._info_lbl.set_markup(
                f'<span foreground="#cc4444">Reset failed: {e}</span>'
            )

    def _on_delete_event(self, _win: Gtk.Window, _event: Gdk.Event) -> bool:
        return False

    def _on_install_autostart(self, _btn: Gtk.Button) -> None:
        if install_autostart(self._working):
            self._autostart_status_lbl.set_markup("Status: <b>Installed</b>")

    def _on_uninstall_autostart(self, _btn: Gtk.Button) -> None:
        if AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
            self._autostart_status_lbl.set_markup("Status: <b>Not installed</b>")
