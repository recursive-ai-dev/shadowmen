import math
from typing import Callable, ClassVar
import cairo

_GLOW_COLOR: tuple[float, float, float, float] = (0.4, 0.8, 1.0, 0.6)


def _ln(cr: cairo.Context, x1: float, y1: float, x2: float, y2: float) -> None:
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()


class CharacterRenderer:
    """Backwards-compatible character renderer with cleaned-up draw methods."""

    _pose_registry: ClassVar[dict[str, Callable[["CharacterRenderer"], None]]] = {}

    def __init__(
        self,
        cr: cairo.Context,
        px: float,
        py: float,
        t: float,
        state: str,
        facing: int,
        s: float,
        leg_amp: float,
        arm_amp: float,
        body_color: tuple[float, float, float, float],
        *,
        glow: bool = False,
        glow_color: tuple[float, float, float, float] | None = None,
        glow_width: float | None = None,
        line_width: float | None = None,
        enable_shadow: bool = True,
        shadow_alpha: float = 0.18,
    ) -> None:
        self.cr = cr
        self.px = px
        self.py = py
        self.t = t
        self.state = state
        self.facing = facing if facing != 0 else 1
        self.s = s
        self.leg_amp = leg_amp
        self.arm_amp = arm_amp
        self.body_color = body_color
        self.glow = glow
        self.glow_color = glow_color if glow_color is not None else _GLOW_COLOR
        self.enable_shadow = enable_shadow
        self.shadow_alpha = shadow_alpha
        self._base_lw = line_width if line_width is not None else 1.0
        self.gw = glow_width if glow_width is not None else (2.7 if glow else 1.0)
        self.hr = s * 0.31 + (s * 0.13 if glow else 0)

    @classmethod
    def register_pose(cls, state: str, draw_fn: Callable[["CharacterRenderer"], None]) -> None:
        cls._pose_registry[state] = draw_fn

    def _set_stroke_style(self) -> None:
        cr = self.cr
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

    def _set_color(self, color: tuple[float, float, float, float] | None = None) -> None:
        self.cr.set_source_rgba(*(color if color is not None else
                                  (self.glow_color if self.glow else self.body_color)))

    def _stroke_width(self, w: float) -> None:
        self.cr.set_line_width(w * self.gw * self._base_lw)

    def render(self) -> None:
        cr = self.cr

        self._set_color()
        self._set_stroke_style()

        if self.enable_shadow and not self.glow and self.state not in ("fall", "jump", "climb"):
            self._draw_ground_shadow()
            self._set_color()

        draw_fn = self._get_pose_dispatch().get(self.state, self._draw_idle)
        draw_fn()

    def _get_pose_dispatch(self) -> dict[str, Callable[[], None]]:
        base = {
            "walk": self._draw_walk_run,
            "run": self._draw_walk_run,
            "climb": self._draw_climb,
            "sit": self._draw_sit,
            "idle": self._draw_idle,
            "wave": self._draw_wave,
            "fall": self._draw_fall,
            "jump": self._draw_jump,
            "crouch": self._draw_crouch,
        }
        for state, fn in self._pose_registry.items():
            base[state] = lambda f=fn: f(self)
        return base

    def _draw_ground_shadow(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        cr.save()
        cr.translate(px, py + 2)
        cr.scale(1.0, 0.22)
        cr.arc(0, 0, s * 0.52, 0, 2 * math.pi)
        alpha = 0.0 if self.glow else self.shadow_alpha
        cr.set_source_rgba(0, 0, 0, alpha)
        cr.fill()
        cr.restore()

    def _draw_walk_run(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        facing = self.facing
        state = self.state

        spd = 2.0 if state == "run" else 1.0
        phase = self.t * 0.22 * spd
        sw = math.sin(phase)
        run_mult = 1.4 if state == "run" else 1.0
        la = sw * self.leg_amp * run_mult
        aa = -sw * self.arm_amp * run_mult
        lean = s * 0.08 * facing if state == "run" else 0.0

        hip_x, hip_y = px + lean, py - s
        sho_x, sho_y = px + lean * 0.5, py - s * 1.85

        cr.save()
        self._set_color()

        self._stroke_width(s * 0.19)
        for sign in (-1, 1):
            _ln(cr, hip_x, hip_y, hip_x + math.sin(la * sign) * s, py)

        self._stroke_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        self._stroke_width(s * 0.15)
        for sign in (-1, 1):
            ang = aa * sign
            hx = sho_x + math.sin(ang) * s * 0.82 * facing
            hy = sho_y + s * 0.60 + math.sin(abs(ang)) * s * 0.12
            _ln(cr, sho_x, sho_y, hx, hy)

        cr.arc(sho_x, sho_y - s * 0.38, self.hr, 0, 2 * math.pi)
        cr.fill()

        cr.restore()

    def _draw_climb(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw, facing = self.gw, self.facing

        phase = self.t * 0.22
        reach = math.sin(phase)
        wd = facing * s * 0.92
        bx = -facing * s * 0.22

        sho_x, sho_y = px + bx * 0.8, py - s * 1.48
        hip_x, hip_y = px + bx * 1.25, py - s * 0.52
        head_x = px + bx * 0.45

        cr.arc(head_x, sho_y - s * 0.36, self.hr, 0, 2 * math.pi)
        cr.fill()

        cr.set_line_width(s * 0.20 * gw)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, sho_x, sho_y, px + wd, sho_y - s * 0.48 - reach * s * 0.38)
        _ln(cr, sho_x, sho_y, px + wd, sho_y - s * 0.02 + reach * s * 0.38)

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, hip_x, hip_y, px + wd, hip_y + s * 0.48 + reach * s * 0.28)
        _ln(cr, hip_x, hip_y, px + wd, hip_y + s * 0.48 - reach * s * 0.28)

    def _draw_sit(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw = self.gw

        bob = math.sin(self.t * 0.04) * 1.6
        base_y = py + bob
        torso_y = py - s * 0.48 + bob

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, px, base_y, px - s * 0.62, torso_y)
        _ln(cr, px, base_y, px + s * 0.62, torso_y)
        _ln(cr, px, torso_y, px - s * 0.22, py - s * 1.42 + bob)

        cr.set_line_width(s * 0.15 * gw)
        shoulder_y = py - s * 0.92 + bob
        _ln(cr, px - s * 0.12, shoulder_y, px - s * 0.84, py - s * 0.56 + bob)
        _ln(cr, px - s * 0.12, shoulder_y, px + s * 0.54, py - s * 0.52 + bob)

        cr.arc(px - s * 0.22, py - s * 1.78 + bob, self.hr, 0, 2 * math.pi)
        cr.fill()

    def _draw_idle(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw = self.gw

        bob = math.sin(self.t * 0.05) * 1.3
        hip_y = py - s * 0.9 + bob
        shoulder_y = py - s * 1.52 + bob
        neck_y = py - s * 1.85 + bob

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, px - s * 0.17, hip_y, px - s * 0.17, py + bob)
        _ln(cr, px + s * 0.17, hip_y, px + s * 0.17, py + bob)
        _ln(cr, px, hip_y, px, neck_y)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, px, shoulder_y, px - s * 0.70, py - s * 1.10 + bob)
        _ln(cr, px, shoulder_y, px + s * 0.70, py - s * 1.10 + bob)

        cr.arc(px, py - s * 2.18 + bob, self.hr, 0, 2 * math.pi)
        cr.fill()

    def _draw_wave(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw = self.gw

        bob = math.sin(self.t * 0.04) * 1.2
        wag = math.sin(self.t * 0.28) * 0.65
        hip_y = py - s * 0.9 + bob
        shoulder_y = py - s * 1.52 + bob
        neck_y = py - s * 1.85 + bob

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, px - s * 0.17, hip_y, px - s * 0.17, py + bob)
        _ln(cr, px + s * 0.17, hip_y, px + s * 0.17, py + bob)
        _ln(cr, px, hip_y, px, neck_y)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, px, shoulder_y, px - s * 0.68, py - s * 1.08 + bob)
        _ln(cr, px, shoulder_y,
            px + math.sin(wag) * s * 0.78,
            neck_y + math.cos(wag) * s * 0.52)

        cr.arc(px, py - s * 2.18 + bob, self.hr, 0, 2 * math.pi)
        cr.fill()

    def _draw_fall(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw = self.gw

        cr.save()
        cr.translate(px, py - s)
        cr.rotate(self.t * 0.25)

        cr.set_source_rgba(*(self.glow_color if self.glow else self.body_color))

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, 0, 0, 0, s)
        _ln(cr, 0, s, -s * 0.55, s * 1.60)
        _ln(cr, 0, s, s * 0.50, s * 1.65)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, 0, s * 0.28, -s * 0.78, s * 0.62)
        _ln(cr, 0, s * 0.28, s * 0.66, -s * 0.12)

        cr.arc(0, -s * 0.32, self.hr, 0, 2 * math.pi)
        cr.fill()

        cr.restore()

    def _draw_jump(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw, facing = self.gw, self.facing

        tilt = facing * s * 0.12
        hip_y = py - s * 0.52
        shoulder_x = px + tilt * 0.5
        shoulder_y = py - s * 1.50
        neck_y = py - s * 1.82

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, px, hip_y, px + tilt, neck_y)
        _ln(cr, px, hip_y, px - facing * s * 0.54, py - s * 0.10)
        _ln(cr, px, hip_y, px - facing * s * 0.42, py - s * 0.28)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, shoulder_x, shoulder_y, px + facing * s * 0.72, neck_y)
        _ln(cr, shoulder_x, shoulder_y, px - facing * s * 0.58, py - s * 1.22)

        cr.arc(px + tilt, py - s * 2.18, self.hr, 0, 2 * math.pi)
        cr.fill()

    def _draw_crouch(self) -> None:
        cr, px, py, s = self.cr, self.px, self.py, self.s
        gw = self.gw

        bob = math.sin(self.t * 0.07) * 0.9
        base_y = py + bob
        knee_y = py - s * 0.62 + bob
        torso_x = px - s * 0.08
        torso_y = py - s * 1.35 + bob
        shoulder_y = py - s * 1.12 + bob

        cr.set_line_width(s * 0.19 * gw)
        _ln(cr, px, base_y, px - s * 0.52, knee_y)
        _ln(cr, px, base_y, px + s * 0.52, knee_y)
        _ln(cr, torso_x, knee_y, torso_x, torso_y)

        cr.set_line_width(s * 0.15 * gw)
        _ln(cr, torso_x, shoulder_y, px - s * 0.55, knee_y)
        _ln(cr, torso_x, shoulder_y, px + s * 0.45, knee_y)

        cr.arc(torso_x, py - s * 1.70 + bob, self.hr, 0, 2 * math.pi)
        cr.fill()


def draw_person(
    cr: cairo.Context,
    px: float,
    py: float,
    t: float,
    state: str,
    facing: int,
    s: float,
    leg_amp: float,
    arm_amp: float,
    body_color: tuple[float, float, float, float],
    *,
    glow: bool = False,
    glow_color: tuple[float, float, float, float] | None = None,
) -> None:
    CharacterRenderer(
        cr, px, py, t, state, facing, s, leg_amp, arm_amp, body_color,
        glow=glow,
        glow_color=glow_color,
    ).render()


def draw_fire(
    cr: cairo.Context,
    x: float,
    y: float,
    t: float,
    s: float,
) -> None:
    cr.save()
    cr.translate(x, y)

    cr.set_source_rgba(1.0, 0.4, 0.1, 0.15)
    cr.arc(0, 0, s * 1.5, 0, 2 * math.pi)
    cr.fill()

    for i in range(3):
        phase = t * 0.15 + i * 2.0
        fx = math.sin(phase) * s * 0.15
        fy = -s * 0.4 - math.cos(phase * 0.5) * s * 0.2
        cr.set_source_rgba(1.0, 0.3 + 0.2 * i, 0.0, 0.8)
        cr.set_line_width(s * 0.12)
        _ln(cr, fx * 0.5, 0, fx, fy)

    cr.set_source_rgba(0.3, 0.2, 0.1, 1.0)
    cr.set_line_width(s * 0.1)
    _ln(cr, -s * 0.3, 0, s * 0.3, -s * 0.05)
    _ln(cr, -s * 0.25, -s * 0.05, s * 0.2, 0)

    cr.restore()


def draw_shelter(
    cr: cairo.Context,
    x: float,
    y: float,
    s: float,
) -> None:
    cr.save()
    cr.translate(x, y)

    cr.set_source_rgba(0.2, 0.15, 0.1, 0.7)
    cr.set_line_width(s * 0.12)

    _ln(cr, -s * 0.8, 0, 0, -s * 1.2)
    _ln(cr, s * 0.8, 0, 0, -s * 1.2)
    _ln(cr, -s * 0.4, -s * 0.6, s * 0.4, -s * 0.6)

    cr.restore()
