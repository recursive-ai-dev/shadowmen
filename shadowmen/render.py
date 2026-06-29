from __future__ import annotations
from typing import Any

import math
from collections.abc import Callable

try:
    import cairo
except ImportError:
    cairo = None


def _ln(cr: Any, x1: float, y1: float, x2: float, y2: float) -> None:
    if cr is None:
        return
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()


class CharacterRenderer:
    _base_lw: float = 1.0

    def __init__(self, cr: Any) -> None:
        self.cr = cr
        # Cache pose dispatch to avoid dict creation in hot loop
        self._poses: dict[
            str,
            Callable[
                [
                    float,
                    float,
                    float,
                    int,
                    float,
                    float,
                    float,
                    tuple[float, float, float, float],
                ],
                None,
            ],
        ] = {
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

    def render(
        self,
        px: float,
        py: float,
        t: float,
        state: str,
        facing: int,
        s: float,
        leg_amp: float,
        arm_amp: float,
        color: tuple[float, float, float, float],
        glow: bool = False,
        glow_color: tuple[float, float, float, float] | None = None,
    ) -> None:
        cr = self.cr
        if cr is None:
            return
        cr.save()
        if glow and glow_color:
            cr.set_source_rgba(*glow_color)
            cr.set_dash([2.0, 1.0])
        else:
            cr.set_source_rgba(*color)
            cr.set_dash([])

        draw_fn = self._poses.get(state, self._draw_idle)
        draw_fn(px, py, t, facing, s, leg_amp, arm_amp, color)
        cr.restore()

    def _draw_walk_run(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        is_run = leg_amp > 0.45
        spd = 0.35 if is_run else 0.22
        phase = t * spd
        sw = math.sin(phase)
        la = sw * leg_amp
        aa = -sw * arm_amp

        # Lean forward when running
        lean = facing * s * 0.15 if is_run else 0.0

        hip_x, hip_y = px, py - s
        sho_x, sho_y = px + lean, py - s * 1.85

        cr.set_line_width(s * 0.19)
        # Legs
        _ln(cr, hip_x, hip_y, hip_x + math.sin(la) * s, py)
        _ln(cr, hip_x, hip_y, hip_x + math.sin(-la) * s, py)

        cr.set_line_width(s * 0.20)
        # Torso
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        cr.set_line_width(s * 0.15)
        # Arms
        arm_len = s * 0.85
        _ln(
            cr,
            sho_x,
            sho_y,
            sho_x + math.sin(aa + (0.2 if is_run else 0)) * arm_len,
            sho_y + s * 0.6,
        )
        _ln(
            cr,
            sho_x,
            sho_y,
            sho_x + math.sin(-aa - (0.2 if is_run else 0)) * arm_len,
            sho_y + s * 0.6,
        )

        # Head
        cr.arc(sho_x + lean * 0.2, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_climb(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        phase = t * 0.15
        sw = math.sin(phase)

        bx = -facing * s * 0.25
        sho_x, sho_y = px + bx * 0.8, py - s * 1.5
        hip_x, hip_y = px + bx * 0.5, py - s * 0.7

        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        cr.set_line_width(s * 0.16)
        # Reaching arms
        _ln(cr, sho_x, sho_y, px + facing * s * 0.2, sho_y - s * 0.4 + sw * s * 0.2)
        _ln(cr, sho_x, sho_y, px + facing * s * 0.2, sho_y - s * 0.2 - sw * s * 0.2)

        # Head
        cr.arc(sho_x + facing * s * 0.1, sho_y - s * 0.35, s * 0.34, 0, 2 * math.pi)
        cr.fill()

        # Legs
        _ln(cr, hip_x, hip_y, px + facing * s * 0.1, py)
        _ln(cr, hip_x, hip_y, px - facing * s * 0.2, py + s * 0.2)

    def _draw_sit(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        bob = math.sin(t * 0.06) * s * 0.05
        hip_x, hip_y = px, py - s * 0.4 + bob
        sho_x, sho_y = px - facing * s * 0.1, py - s * 1.2 + bob

        cr.set_line_width(s * 0.22)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        # Knees
        cr.set_line_width(s * 0.18)
        knee_x, knee_y = px + facing * s * 0.6, py - s * 0.4 + bob
        _ln(cr, hip_x, hip_y, knee_x, knee_y)
        _ln(cr, knee_x, knee_y, knee_x + facing * s * 0.1, py)

        # Arms resting on knees
        _ln(cr, sho_x, sho_y, knee_x, knee_y - s * 0.1)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_idle(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        bob = math.sin(t * 0.05) * s * 0.04
        hip_x, hip_y = px, py - s * 0.9 + bob
        sho_x, sho_y = px, py - s * 1.8 + bob

        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        cr.set_line_width(s * 0.18)
        # Legs
        _ln(cr, hip_x, hip_y, px - s * 0.2, py)
        _ln(cr, hip_x, hip_y, px + s * 0.2, py)

        # Arms at sides
        _ln(cr, sho_x, sho_y, sho_x - s * 0.2, sho_y + s * 0.7)
        _ln(cr, sho_x, sho_y, sho_x + s * 0.2, sho_y + s * 0.7)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_wave(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        bob = math.sin(t * 0.05) * s * 0.04
        wave = math.sin(t * 0.25) * s * 0.3
        hip_x, hip_y = px, py - s * 0.9 + bob
        sho_x, sho_y = px, py - s * 1.8 + bob

        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        cr.set_line_width(s * 0.18)
        _ln(cr, hip_x, hip_y, px - s * 0.2, py)
        _ln(cr, hip_x, hip_y, px + s * 0.2, py)

        # One arm down, one waving
        _ln(cr, sho_x, sho_y, sho_x - facing * s * 0.2, sho_y + s * 0.7)
        # Waving arm
        _ln(cr, sho_x, sho_y, sho_x + facing * s * 0.4 + wave, sho_y - s * 0.6)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_fall(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        phase = t * 0.3
        hip_x, hip_y = px, py - s * 1.2
        sho_x, sho_y = px + math.sin(phase) * s * 0.1, py - s * 2.0

        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        # Flailing
        cr.set_line_width(s * 0.16)
        _ln(cr, hip_x, hip_y, hip_x + math.sin(phase) * s, py - s * 0.2)
        _ln(cr, hip_x, hip_y, hip_x + math.cos(phase) * s, py - s * 0.4)

        _ln(cr, sho_x, sho_y, sho_x + math.sin(phase + 2) * s, sho_y - s * 0.2)
        _ln(cr, sho_x, sho_y, sho_x + math.cos(phase + 2) * s, sho_y + s * 0.2)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_jump(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        hip_x, hip_y = px, py - s * 1.4
        sho_x, sho_y = px + facing * s * 0.2, py - s * 2.2

        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        # Tucked legs
        cr.set_line_width(s * 0.18)
        _ln(cr, hip_x, hip_y, hip_x - facing * s * 0.3, hip_y + s * 0.6)
        _ln(cr, hip_x, hip_y, hip_x + facing * s * 0.1, hip_y + s * 0.7)

        # Reaching arms
        _ln(cr, sho_x, sho_y, sho_x + facing * s * 0.5, sho_y - s * 0.3)
        _ln(cr, sho_x, sho_y, sho_x + facing * s * 0.4, sho_y - s * 0.5)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_crouch(self, px: float, py: float, t: float, facing: int, s: float, leg_amp: float, arm_amp: float, color: tuple[float, float, float, float]) -> None:
        cr = self.cr
        hip_x, hip_y = px, py - s * 0.3
        sho_x, sho_y = px + facing * s * 0.2, py - s * 0.8

        cr.set_line_width(s * 0.24)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)

        # Low legs
        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, px - s * 0.5, py)
        _ln(cr, hip_x, hip_y, px + s * 0.5, py)

        # Arms hugging knees
        _ln(cr, sho_x, sho_y, px, py - s * 0.2)

        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()


_cached_renderer: CharacterRenderer | None = None


def draw_person(
    cr: Any,
    px: float,
    py: float,
    t: float,
    state: str,
    facing: int,
    s: float,
    leg_amp: float,
    arm_amp: float,
    color: tuple[float, float, float, float],
    glow: bool = False,
    glow_color: tuple[float, float, float, float] | None = None,
) -> None:
    global _cached_renderer
    if _cached_renderer is None or _cached_renderer.cr != cr:
        _cached_renderer = CharacterRenderer(cr)
    _cached_renderer.render(
        px, py, t, state, facing, s, leg_amp, arm_amp, color, glow, glow_color
    )


def draw_fire(cr: Any, x: float, y: float, t: float, s: float) -> None:
    if cr is None:
        return
    cr.save()
    cr.translate(x, y)

    # Flickering flame
    flicker = 1.0 + 0.2 * math.sin(t * 0.4)
    cr.set_source_rgba(1.0, 0.4, 0.1, 0.2 * flicker)
    cr.arc(0, 0, s * 1.5 * flicker, 0, 2 * math.pi)
    cr.fill()

    # Core
    cr.set_source_rgba(1.0, 0.8, 0.2, 0.6 * flicker)
    cr.arc(0, -s * 0.2, s * 0.5 * flicker, 0, 2 * math.pi)
    cr.fill()

    cr.restore()


def draw_shelter(cr: Any, x: float, y: float, s: float) -> None:
    if cr is None:
        return
    cr.save()
    cr.translate(x, y)
    cr.set_source_rgba(0.2, 0.15, 0.1, 0.7)
    cr.set_line_width(s * 0.12)
    # Tipi shape
    _ln(cr, -s * 0.8, 0, 0, -s * 1.2)
    _ln(cr, s * 0.8, 0, 0, -s * 1.2)
    _ln(cr, -s * 0.4, 0, 0, -s * 1.2)
    _ln(cr, s * 0.4, 0, 0, -s * 1.2)
    cr.restore()
