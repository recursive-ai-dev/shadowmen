from __future__ import annotations
import math
import cairo
from typing import Dict, Callable, Tuple, Optional

def _ln(cr: cairo.Context, x1: float, y1: float, x2: float, y2: float) -> None:
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()

class CharacterRenderer:
    _base_lw: float = 1.0

    def __init__(self, cr: cairo.Context):
        self.cr = cr
        # Cache pose dispatch to avoid dict creation in hot loop
        self._poses: Dict[str, Callable[[float, float, float, int, float, float, float, Tuple[float, float, float, float]], None]] = {
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

    def render(self, px: float, py: float, t: float, state: str, facing: int, s: float,
               leg_amp: float, arm_amp: float, color: Tuple[float, float, float, float],
               glow: bool = False, glow_color: Optional[Tuple[float, float, float, float]] = None) -> None:
        cr = self.cr
        if glow and glow_color:
            cr.set_source_rgba(*glow_color)
            cr.set_dash([2.0, 1.0])
        else:
            cr.set_source_rgba(*color)
            cr.set_dash([])

        draw_fn = self._poses.get(state, self._draw_idle)
        draw_fn(px, py, t, facing, s, leg_amp, arm_amp, color)

    def _draw_walk_run(self, px, py, t, facing, s, leg_amp, arm_amp, color):
        cr = self.cr
        spd = 2.0 if leg_amp > 0.4 else 1.0 # Approximate
        phase = t * 0.22 * spd
        sw = math.sin(phase)
        la = sw * leg_amp
        aa = -sw * arm_amp
        hip_x, hip_y = px, py - s
        sho_x, sho_y = px, py - s * 1.85

        cr.set_line_width(s * 0.19)
        _ln(cr, hip_x, hip_y, hip_x + math.sin(la) * s, py)
        _ln(cr, hip_x, hip_y, hip_x + math.sin(-la) * s, py)
        cr.set_line_width(s * 0.20)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)
        cr.set_line_width(s * 0.15)
        _ln(cr, sho_x, sho_y, sho_x + math.sin(aa) * s * 0.8, sho_y + s * 0.6)
        _ln(cr, sho_x, sho_y, sho_x + math.sin(-aa) * s * 0.8, sho_y + s * 0.6)
        cr.arc(sho_x, sho_y - s * 0.38, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_climb(self, px, py, t, facing, s, leg_amp, arm_amp, color):
        cr = self.cr
        bx = -facing * s * 0.22
        sho_x, sho_y = px + bx * 0.8, py - s * 1.48
        cr.arc(px + bx * 0.45, sho_y - s * 0.36, s * 0.35, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(s * 0.20)
        _ln(cr, px + bx * 1.25, py - s * 0.52, sho_x, sho_y)

    def _draw_sit(self, px, py, t, facing, s, leg_amp, arm_amp, color):
        cr = self.cr
        bob = math.sin(t * 0.04) * 1.6
        cr.set_line_width(s * 0.19)
        _ln(cr, px, py + bob, px - s * 0.62, py - s * 0.48 + bob)
        cr.arc(px - s * 0.22, py - s * 1.78 + bob, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_idle(self, px, py, t, facing, s, leg_amp, arm_amp, color):
        cr = self.cr
        bob = math.sin(t * 0.05) * 1.3
        cr.set_line_width(s * 0.19)
        _ln(cr, px, py - s * 0.9 + bob, px, py - s * 1.85 + bob)
        cr.arc(px, py - s * 2.18 + bob, s * 0.35, 0, 2 * math.pi)
        cr.fill()

    def _draw_wave(self, px, py, t, facing, s, leg_amp, arm_amp, color): self._draw_idle(px, py, t, facing, s, leg_amp, arm_amp, color)
    def _draw_fall(self, px, py, t, facing, s, leg_amp, arm_amp, color): self._draw_idle(px, py, t, facing, s, leg_amp, arm_amp, color)
    def _draw_jump(self, px, py, t, facing, s, leg_amp, arm_amp, color): self._draw_idle(px, py, t, facing, s, leg_amp, arm_amp, color)
    def _draw_crouch(self, px, py, t, facing, s, leg_amp, arm_amp, color): self._draw_idle(px, py, t, facing, s, leg_amp, arm_amp, color)

_cached_renderer: Optional[CharacterRenderer] = None

def draw_person(cr, px, py, t, state, facing, s, leg_amp, arm_amp, color, glow=False, glow_color=None):
    global _cached_renderer
    if _cached_renderer is None or _cached_renderer.cr != cr:
        _cached_renderer = CharacterRenderer(cr)
    _cached_renderer.render(px, py, t, state, facing, s, leg_amp, arm_amp, color, glow, glow_color)

def draw_fire(cr, x, y, t, s):
    cr.save()
    cr.translate(x, y)
    cr.set_source_rgba(1.0, 0.4, 0.1, 0.15)
    cr.arc(0, 0, s * 1.5, 0, 2 * math.pi)
    cr.fill()
    cr.restore()

def draw_shelter(cr, x, y, s):
    cr.save()
    cr.translate(x, y)
    cr.set_source_rgba(0.2, 0.15, 0.1, 0.7)
    cr.set_line_width(s * 0.12)
    _ln(cr, -s * 0.8, 0, 0, -s * 1.2)
    _ln(cr, s * 0.8, 0, 0, -s * 1.2)
    cr.restore()
