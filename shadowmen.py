#!/usr/bin/env python3
"""
shadowmen.py — an evolving colony of shadow people with a predator,
               sexual selection, island speciation, and an arms race.

  --count N           population size (default 8)
  --predator          spawn a red predator that hunts — and speeds up with each kill
  --evo-speed N       run the evolutionary clock N× faster (good for watching traits shift)
  --install-autostart write an autostart .desktop entry
  --reset             wipe the saved population and start fresh

Press Ctrl-C to quit.  Population auto-saved to ~/.shadowmen_pop.json
"""

import sys, math, random, signal, argparse, json, subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib
    import cairo
except ImportError:
    sys.exit("Install: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0")

# ── tunables ──────────────────────────────────────────────────────────────────
EVOLVE_EVERY       = 600    # ticks at 30 fps ≈ 20 s (divided by --evo-speed)
SAVE_FILE          = Path.home() / ".shadowmen_pop.json"

FLEE_RADIUS_X      = 200    # px horizontal trigger distance from predator
FLEE_RADIUS_Y      = 55     # px vertical floor tolerance
PANIC_RADIUS       = 130    # px radius of social panic spread
KILL_EFFECT_TICKS  = 48     # how many frames the kill splat fades over

PRED_BASE_SPEED    = 6.2    # starts faster than avg prey run speed (~5.3)
PRED_SPEED_INC     = 0.22   # speed gain per kill — arms race escalates fast
PRED_SPEED_CAP     = 13.0
_PRED_BODY = (0.68, 0.08, 0.02, 0.95)
_PRED_GLOW = (1.00, 0.30, 0.04, 0.62)

# ── genome ────────────────────────────────────────────────────────────────────
TRAITS = {
    #  name           lo       hi      default
    "walk_speed":  (1.2,    4.8,    2.2),
    "run_mult":    (1.8,    3.5,    2.4),
    "scale":       (13.0,  28.0,   18.0),
    "climb_prob":  (0.002,  0.09,  0.018),
    "sit_prob":    (0.0004, 0.007, 0.0013),
    "run_prob":    (0.0004, 0.007, 0.0024),
    "wave_prob":   (0.0004, 0.007, 0.0013),
    "social_r":    (0.6,    4.2,   1.8),
    "leg_amp":     (0.20,   0.58,  0.36),
    "arm_amp":     (0.14,   0.48,  0.28),
    "hue_r":       (-0.04,  0.15,  0.0),
    "hue_b":       (-0.04,  0.24,  0.0),
}

@dataclass
class Genome:
    walk_speed: float = 2.2
    run_mult:   float = 2.4
    scale:      float = 18.0
    climb_prob: float = 0.018
    sit_prob:   float = 0.0013
    run_prob:   float = 0.0024
    wave_prob:  float = 0.0013
    social_r:   float = 1.8
    leg_amp:    float = 0.36
    arm_amp:    float = 0.28
    hue_r:      float = 0.0
    hue_b:      float = 0.0
    fitness:    float = field(default=0.0, compare=False)

    @classmethod
    def random(cls):
        kwargs = {k: random.uniform(v[0], v[1]) for k, v in TRAITS.items()}
        kwargs["fitness"] = 0.0
        return cls(**kwargs)

    @classmethod
    def crossover(cls, a, b, mutation_rate=0.18):
        """Uniform crossover + per-trait gaussian mutation."""
        kwargs = {}
        for trait, (lo, hi, _) in TRAITS.items():
            val = getattr(a, trait) if random.random() < 0.5 else getattr(b, trait)
            if random.random() < mutation_rate:
                val += random.gauss(0, (hi - lo) * 0.10)
                val = max(lo, min(hi, val))
            kwargs[trait] = val
        kwargs["fitness"] = 0.0
        return cls(**kwargs)

    def body_color(self):
        return (
            max(0.0, min(0.28, 0.04 + self.hue_r)),
            0.04,
            max(0.0, min(0.40, 0.12 + self.hue_b)),
            0.95,
        )

    def to_dict(self):
        return {k: getattr(self, k) for k in TRAITS}

    @classmethod
    def from_dict(cls, d):
        kwargs = {k: float(d.get(k, v[2])) for k, v in TRAITS.items()}
        kwargs["fitness"] = 0.0
        return cls(**kwargs)


# ── kill effect ───────────────────────────────────────────────────────────────
@dataclass
class KillEffect:
    x:       float
    y:       float
    age:     int = 0
    max_age: int = KILL_EFFECT_TICKS


# ── window list ───────────────────────────────────────────────────────────────
def get_windows(sw, sh):
    try:
        raw = subprocess.check_output(
            ["wmctrl", "-l", "-G"],
            text=True, stderr=subprocess.DEVNULL, timeout=1,
        )
        wins = []
        for line in raw.splitlines():
            p = line.split()
            if len(p) < 7:
                continue
            try:
                if int(p[1]) < 0:
                    continue
                x, y, w, h = int(p[2]), int(p[3]), int(p[4]), int(p[5])
            except ValueError:
                continue
            if w < 80 or h < 80:
                continue
            if w >= sw - 10 and h >= sh - 10:
                continue
            wins.append((x, y, w, h))
        return wins
    except Exception:
        return []


# ── drawing ───────────────────────────────────────────────────────────────────
_GLOW_COLOR = (1.0, 1.0, 0.85, 0.52)


def _ln(cr, x1, y1, x2, y2):
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()


def draw_person(cr, px, py, t, state, facing, S, leg_amp, arm_amp, body_color,
                glow=False, glow_color=None):
    """
    Render one stick figure.
    (px, py)    foot / ground contact point.
    facing      +1 right / −1 left (during climb: which wall).
    glow        if True, draw the wide bright halo pass.
    glow_color  override for halo RGBA (default: warm white).
    """
    if glow:
        cr.set_source_rgba(*(glow_color if glow_color is not None else _GLOW_COLOR))
        gw = 2.7
    else:
        cr.set_source_rgba(*body_color)
        gw = 1.0

    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)

    if state not in ("fall", "jump", "climb") and not glow:
        cr.save()
        cr.translate(px, py + 2)
        cr.scale(1.0, 0.22)
        cr.arc(0, 0, S * 0.52, 0, 2 * math.pi)
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.fill()
        cr.restore()
        cr.set_source_rgba(*body_color)

    hr = S * 0.31 + (S * 0.13 if glow else 0)

    if state in ("walk", "run"):
        spd   = 2.0 if state == "run" else 1.0
        phase = t * 0.22 * spd
        sw    = math.sin(phase)
        la    = sw * leg_amp * (1.4 if state == "run" else 1.0)
        aa    = -sw * arm_amp * (1.4 if state == "run" else 1.0)
        lean  = S * 0.08 * facing if state == "run" else 0.0

        hip_x, hip_y = px + lean,       py - S
        sho_x, sho_y = px + lean * 0.5, py - S * 1.85

        cr.set_line_width(S * 0.19 * gw)
        for sign in (-1, 1):
            _ln(cr, hip_x, hip_y, hip_x + math.sin(la * sign) * S, py)
        cr.set_line_width(S * 0.20 * gw)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)
        cr.set_line_width(S * 0.15 * gw)
        for sign in (-1, 1):
            ang = aa * sign
            hx  = sho_x + math.sin(ang) * S * 0.82 * facing
            hy  = sho_y + S * 0.60 + math.sin(abs(ang)) * S * 0.12
            _ln(cr, sho_x, sho_y, hx, hy)
        cr.arc(sho_x, sho_y - S * 0.38, hr, 0, 2 * math.pi)
        cr.fill()

    elif state == "climb":
        phase  = t * 0.22
        reach  = math.sin(phase)
        wd     = facing * S * 0.92   # vector from person centre to wall surface
        bx     = -facing * S * 0.22  # body hangs slightly away from wall

        sho_x, sho_y = px + bx * 0.8,  py - S * 1.48
        hip_x, hip_y = px + bx * 1.25, py - S * 0.52
        head_x       = px + bx * 0.45

        cr.arc(head_x, sho_y - S * 0.36, hr, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(S * 0.20 * gw)
        _ln(cr, hip_x, hip_y, sho_x, sho_y)
        cr.set_line_width(S * 0.15 * gw)
        # hands alternate: one grips high, one grips low
        _ln(cr, sho_x, sho_y, px + wd, sho_y - S * 0.48 - reach * S * 0.38)
        _ln(cr, sho_x, sho_y, px + wd, sho_y - S * 0.02 + reach * S * 0.38)
        cr.set_line_width(S * 0.19 * gw)
        # feet brace alternately against the wall
        _ln(cr, hip_x, hip_y, px + wd, hip_y + S * 0.48 + reach * S * 0.28)
        _ln(cr, hip_x, hip_y, px + wd, hip_y + S * 0.48 - reach * S * 0.28)

    elif state == "sit":
        bob = math.sin(t * 0.04) * 1.6
        cr.set_line_width(S * 0.19 * gw)
        _ln(cr, px, py + bob, px - S * 0.62, py - S * 0.48 + bob)
        _ln(cr, px, py + bob, px + S * 0.62, py - S * 0.48 + bob)
        _ln(cr, px, py - S * 0.48 + bob, px - S * 0.22, py - S * 1.42 + bob)
        cr.set_line_width(S * 0.15 * gw)
        _ln(cr, px - S * 0.12, py - S * 0.92 + bob,
               px - S * 0.84, py - S * 0.56 + bob)
        _ln(cr, px - S * 0.12, py - S * 0.92 + bob,
               px + S * 0.54, py - S * 0.52 + bob)
        cr.arc(px - S * 0.22, py - S * 1.78 + bob, hr, 0, 2 * math.pi)
        cr.fill()

    elif state == "idle":
        bob = math.sin(t * 0.05) * 1.3
        cr.set_line_width(S * 0.19 * gw)
        _ln(cr, px - S * 0.17, py - S * 0.9 + bob, px - S * 0.17, py + bob)
        _ln(cr, px + S * 0.17, py - S * 0.9 + bob, px + S * 0.17, py + bob)
        _ln(cr, px, py - S * 0.9 + bob, px, py - S * 1.85 + bob)
        cr.set_line_width(S * 0.15 * gw)
        _ln(cr, px, py - S * 1.52 + bob, px - S * 0.70, py - S * 1.10 + bob)
        _ln(cr, px, py - S * 1.52 + bob, px + S * 0.70, py - S * 1.10 + bob)
        cr.arc(px, py - S * 2.18 + bob, hr, 0, 2 * math.pi)
        cr.fill()

    elif state == "wave":
        bob = math.sin(t * 0.04) * 1.2
        wag = math.sin(t * 0.28) * 0.65
        cr.set_line_width(S * 0.19 * gw)
        _ln(cr, px - S * 0.17, py - S * 0.9 + bob, px - S * 0.17, py + bob)
        _ln(cr, px + S * 0.17, py - S * 0.9 + bob, px + S * 0.17, py + bob)
        _ln(cr, px, py - S * 0.9 + bob, px, py - S * 1.85 + bob)
        cr.set_line_width(S * 0.15 * gw)
        _ln(cr, px, py - S * 1.52 + bob, px - S * 0.68, py - S * 1.08 + bob)
        whx = px + math.sin(wag) * S * 0.78
        why = py - S * 1.85 + bob + math.cos(wag) * S * 0.52
        _ln(cr, px, py - S * 1.52 + bob, whx, why)
        cr.arc(px, py - S * 2.18 + bob, hr, 0, 2 * math.pi)
        cr.fill()

    elif state == "fall":
        cr.save()
        cr.translate(px, py - S)
        cr.rotate(t * 0.25)
        if glow:
            cr.set_source_rgba(*(glow_color if glow_color is not None else _GLOW_COLOR))
        else:
            cr.set_source_rgba(*body_color)
        cr.set_line_width(S * 0.19 * gw)
        _ln(cr, 0, 0, 0, S)
        cr.set_line_width(S * 0.15 * gw)
        _ln(cr, 0, S * 0.28, -S * 0.78, S * 0.62)
        _ln(cr, 0, S * 0.28,  S * 0.66, -S * 0.12)
        cr.set_line_width(S * 0.19 * gw)
        _ln(cr, 0, S, -S * 0.55, S * 1.60)
        _ln(cr, 0, S,  S * 0.50, S * 1.65)
        cr.arc(0, -S * 0.32, hr, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    elif state == "jump":
        tilt = facing * S * 0.12
        cr.set_line_width(S * 0.19 * gw)
        # torso leans forward; legs kick back
        _ln(cr, px,        py - S * 0.52, px + tilt, py - S * 1.82)
        _ln(cr, px,        py - S * 0.52, px - facing * S * 0.54, py - S * 0.10)
        _ln(cr, px,        py - S * 0.52, px - facing * S * 0.42, py - S * 0.28)
        cr.set_line_width(S * 0.15 * gw)
        # leading arm reaches forward-up; trailing arm sweeps back
        _ln(cr, px + tilt * 0.5, py - S * 1.50,
               px + facing * S * 0.72, py - S * 1.82)
        _ln(cr, px + tilt * 0.5, py - S * 1.50,
               px - facing * S * 0.58, py - S * 1.22)
        cr.arc(px + tilt, py - S * 2.18, hr, 0, 2 * math.pi)
        cr.fill()

    elif state == "crouch":
        bob = math.sin(t * 0.07) * 0.9
        cr.set_line_width(S * 0.19 * gw)
        # thighs splayed wide from feet
        _ln(cr, px, py + bob, px - S * 0.52, py - S * 0.62 + bob)
        _ln(cr, px, py + bob, px + S * 0.52, py - S * 0.62 + bob)
        # hunched torso
        _ln(cr, px - S * 0.08, py - S * 0.62 + bob,
               px - S * 0.08, py - S * 1.35 + bob)
        cr.set_line_width(S * 0.15 * gw)
        # arms resting on knees
        _ln(cr, px - S * 0.08, py - S * 1.12 + bob,
               px - S * 0.55, py - S * 0.62 + bob)
        _ln(cr, px - S * 0.08, py - S * 1.12 + bob,
               px + S * 0.45, py - S * 0.62 + bob)
        cr.arc(px - S * 0.08, py - S * 1.70 + bob, hr, 0, 2 * math.pi)
        cr.fill()


# ── person ────────────────────────────────────────────────────────────────────
class Person:
    def __init__(self, sw, sh, genome=None):
        self.sw, self.sh = sw, sh
        self.genome      = genome or Genome.random()
        S                = self.genome.scale

        self.x       = float(random.randint(int(S * 2), int(sw - S * 2)))
        self.y       = float(sh - S * 0.3)
        self.floor_y = self.y
        self.vx      = random.choice([-1, 1]) * self.genome.walk_speed
        self.vy      = 0.0
        self.facing  = 1 if self.vx > 0 else -1
        self.state   = "walk"
        self.t       = random.uniform(0, 400)
        self.timer   = 0
        self.wall_x   = None
        self.wall_side = 0
        # evolution bookkeeping
        self.social_count = 0   # wave interactions this generation
        self.fleeing      = False

    def update(self, windows):
        self.t += 1
        self.genome.fitness += 0.004

        if self.state in ("walk", "run"):
            self._walk_step(windows)
        elif self.state == "climb":
            self._climb_step(windows)
        elif self.state == "fall":
            self._fall_step(windows)
        elif self.state == "jump":
            self._jump_step(windows)
        elif self.state in ("idle", "sit", "wave", "crouch"):
            self.timer -= 1
            if self.timer <= 0:
                self._resume_walk()

    def draw(self, cr):
        g     = self.genome
        color = g.body_color()
        args  = (cr, self.x, self.y, self.t, self.state, self.facing,
                 g.scale, g.leg_amp, g.arm_amp, color)
        draw_person(*args, glow=True)
        draw_person(*args, glow=False)

    # ── movement steps ────────────────────────────────────────────────────────
    def _walk_step(self, windows):
        g, S = self.genome, self.genome.scale
        self.x += self.vx
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

        if self.x <= S:
            self.x = S; self.vx = abs(self.vx); self.facing = 1
            if random.random() < g.climb_prob * 8:
                self._begin_climb(0.0, -1); return
        elif self.x >= self.sw - S:
            self.x = self.sw - S; self.vx = -abs(self.vx); self.facing = -1
            if random.random() < g.climb_prob * 8:
                self._begin_climb(float(self.sw), 1); return

        for (wx, wy, ww, wh) in windows:
            if abs(self.y - wy) < 5 and wx + 4 < self.x < wx + ww - 4:
                self.y = self.floor_y = float(wy)
            elif abs(self.x - wx) < S * 1.4 and wy < self.y < wy + wh:
                if random.random() < g.climb_prob:
                    self._begin_climb(float(wx), self.facing); return
            elif abs(self.x - (wx + ww)) < S * 1.4 and wy < self.y < wy + wh:
                if random.random() < g.climb_prob:
                    self._begin_climb(float(wx + ww), self.facing); return

        floor = self._find_floor(windows)
        if self.y < floor - 3:
            self.state = "fall"; self.vy = 0.0; return
        self.y = self.floor_y = floor

        if not self.fleeing:
            r = random.random()
            if r < g.sit_prob:
                self._pause("sit", random.randint(100, 380))
            elif r < g.sit_prob + g.wave_prob:
                self._pause("wave", random.randint(80, 220))
            elif r < g.sit_prob + g.wave_prob + g.run_prob:
                if self.state == "walk":
                    self.state = "run"
                    self.vx = math.copysign(g.walk_speed * g.run_mult, self.vx)
                elif random.random() < 0.35:
                    # running: leap instead of slowing to a walk
                    self.state = "jump"
                    self.vy = -random.uniform(8.0, 11.5)
                else:
                    self.state = "walk"
                    self.vx = math.copysign(g.walk_speed, self.vx)
            elif r < g.sit_prob + g.wave_prob + g.run_prob + 0.0014:
                if self.state == "walk":
                    self._pause("crouch", random.randint(35, 75))

    def _climb_step(self, windows):
        g, S = self.genome, self.genome.scale
        self.y -= 2.5
        self.x  = self.wall_x + (-self.wall_side) * S * 0.92

        for (wx, wy, ww, wh) in windows:
            near = abs(self.wall_x - wx) < 8 or abs(self.wall_x - (wx + ww)) < 8
            if near and self.y <= wy + S:
                self.y = self.floor_y = float(wy)
                self.genome.fitness += 3.0
                self._resume_walk(side=self.wall_side)
                return

        if self.y < g.scale * 1.5:
            self.state = "fall"
            self.vy    = -0.5
            self.vx    = -self.wall_side * random.uniform(2.0, 4.5)

    def _fall_step(self, windows):
        S = self.genome.scale
        self.x   = max(S, min(self.sw - S, self.x + self.vx * 0.55))
        self.vy += 0.65
        self.y  += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy = 0.0
            self.genome.fitness -= 0.8
            if not self.vx:
                self.vx = random.choice([-1, 1]) * self.genome.walk_speed
            self.state  = "walk"
            self.facing = 1 if self.vx > 0 else -1

    def _jump_step(self, windows):
        S = self.genome.scale
        self.x   = max(S, min(self.sw - S, self.x + self.vx))
        self.vy += 0.65
        self.y  += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy = 0.0
            self.state  = "run"
            self.facing = 1 if self.vx > 0 else -1

    def _find_floor(self, windows):
        g = float(self.sh) - self.genome.scale * 0.3
        for (wx, wy, ww, wh) in windows:
            if wx + 4 < self.x < wx + ww - 4 and self.y <= wy + 3:
                g = min(g, float(wy))
        return g

    def _begin_climb(self, wall_x, side):
        self.state = "climb"; self.wall_x = wall_x
        self.wall_side = side; self.facing = side; self.vx = 0.0

    def _pause(self, state, ticks):
        self.state = state; self.timer = ticks; self.vx = 0.0

    def _resume_walk(self, side=None):
        self.state = "walk"; self.wall_x = None
        spd = self.genome.walk_speed
        self.vx = (side * spd) if side is not None else (self.vx or random.choice([-1,1]) * spd)
        self.facing = 1 if self.vx > 0 else -1


# ── predator ──────────────────────────────────────────────────────────────────
class Predator:
    """Red shadow that hunts colony members and gets faster with each kill."""
    SCALE = 22.0

    def __init__(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.x       = float(sw // 2)
        self.y       = float(sh - self.SCALE * 0.3)
        self.floor_y = self.y
        self.vx      = PRED_BASE_SPEED
        self.vy      = 0.0
        self.facing  = 1
        self.speed   = PRED_BASE_SPEED
        self.t       = 0
        self.kills   = 0
        self.state   = "run"

    def update(self, people, windows):
        self.t += 1
        S = self.SCALE

        # chase nearest person on the main floor (no wall climbing)
        floor_people = [p for p in people
                        if abs(p.floor_y - self.floor_y) < FLEE_RADIUS_Y
                        and p.state not in ("fall",)]
        if floor_people:
            target  = min(floor_people, key=lambda p: abs(p.x - self.x))
            self.vx = math.copysign(self.speed, target.x - self.x)
        else:
            # wander
            if self.x <= S:
                self.vx = self.speed; self.facing = 1
            elif self.x >= self.sw - S:
                self.vx = -self.speed; self.facing = -1

        self.x      = max(S, min(self.sw - S, self.x + self.vx))
        self.facing = 1 if self.vx >= 0 else -1

        # simple gravity (predator stays on screen floor only)
        floor = float(self.sh) - S * 0.3
        self.vy += 0.65
        self.y   = min(self.y + self.vy, floor)
        if self.y >= floor:
            self.vy = 0.0; self.y = self.floor_y = floor

        self.state = "run"

    def catch_radius(self):
        return self.SCALE * 0.85

    def on_kill(self):
        self.kills += 1
        self.speed  = min(PRED_SPEED_CAP, self.speed + PRED_SPEED_INC)
        print(f"  💀 kill #{self.kills}! predator speed → {self.speed:.2f}")

    def draw(self, cr):
        args = (cr, self.x, self.y, self.t, self.state, self.facing,
                self.SCALE, 0.50, 0.42, _PRED_BODY)
        draw_person(*args, glow=True,  glow_color=_PRED_GLOW)
        draw_person(*args, glow=False)


# ── colony ────────────────────────────────────────────────────────────────────
class Colony:
    def __init__(self, count, sw, sh, *, use_predator=False, evolve_every=EVOLVE_EVERY):
        self.count        = count
        self.sw, self.sh  = sw, sh
        self.evolve_every = evolve_every
        self.tick_n       = 0
        self.generation   = 0
        self.kill_effects = []
        self.predator     = Predator(sw, sh) if use_predator else None
        self.people       = self._load_or_init()

    # ── persistence ───────────────────────────────────────────────────────────
    def _load_or_init(self):
        if SAVE_FILE.exists():
            try:
                data    = json.loads(SAVE_FILE.read_text())
                genomes = [Genome.from_dict(d) for d in data["genomes"]]
                self.generation = int(data.get("generation", 0))
                while len(genomes) < self.count:
                    genomes.append(Genome.random())
                genomes = genomes[:self.count]
                print(f"Loaded generation {self.generation} ({len(genomes)} souls)")
                return [Person(self.sw, self.sh, g) for g in genomes]
            except Exception as e:
                print(f"Save file unreadable ({e}), starting fresh.")
        return [Person(self.sw, self.sh) for _ in range(self.count)]

    def save(self):
        SAVE_FILE.write_text(json.dumps({
            "generation": self.generation,
            "genomes":    [p.genome.to_dict() for p in self.people],
        }, indent=2))

    # ── per-frame update ──────────────────────────────────────────────────────
    def tick(self, windows):
        self.tick_n += 1

        for p in self.people:
            p.update(windows)

        self._handle_interactions()

        if self.predator:
            self._handle_predator(windows)

        # age kill effects
        for ke in self.kill_effects:
            ke.age += 1
        self.kill_effects = [ke for ke in self.kill_effects if ke.age < ke.max_age]

        if self.tick_n % self.evolve_every == 0:
            self._evolve()
            self.save()

    # ── social interactions ───────────────────────────────────────────────────
    def _handle_interactions(self):
        people = self.people
        for i in range(len(people)):
            a = people[i]
            for j in range(i + 1, len(people)):
                b = people[j]
                if abs(a.y - b.y) > max(a.genome.scale, b.genome.scale) * 1.5:
                    continue
                threshold = ((a.genome.social_r + b.genome.social_r) * 0.5
                             * (a.genome.scale + b.genome.scale) * 0.5)
                dist = abs(a.x - b.x)

                if dist < threshold:
                    if (not a.fleeing and not b.fleeing
                            and a.state in ("walk", "idle")
                            and b.state in ("walk", "idle")
                            and random.random() < 0.006):
                        a.facing = 1 if b.x > a.x else -1
                        b.facing = 1 if a.x > b.x else -1
                        a._pause("wave", random.randint(60, 130))
                        b._pause("wave", random.randint(60, 130))
                        a.genome.fitness += 0.6;  a.social_count += 1
                        b.genome.fitness += 0.6;  b.social_count += 1

                    elif (a.state == "walk" and b.state == "walk"
                          and dist < (a.genome.scale + b.genome.scale) * 0.7):
                        into = ((a.x < b.x and a.vx > 0 and b.vx < 0) or
                                (a.x > b.x and a.vx < 0 and b.vx > 0))
                        if into:
                            a.vx, b.vx = -a.vx, -b.vx
                            a.facing = 1 if a.vx > 0 else -1
                            b.facing = 1 if b.vx > 0 else -1

    # ── predator logic ────────────────────────────────────────────────────────
    def _handle_predator(self, windows):
        pred = self.predator
        pred.update(self.people, windows)

        # ① reset flee flags
        for p in self.people:
            p.fleeing = False

        # ② direct sighting: same floor, within radius
        for p in self.people:
            if (abs(p.x - pred.x)       < FLEE_RADIUS_X
                    and abs(p.floor_y - pred.floor_y) < FLEE_RADIUS_Y):
                p.fleeing = True

        # ③ panic contagion (second pass so order doesn't matter)
        scared_pos = [(p.x, p.y) for p in self.people if p.fleeing]
        if scared_pos:
            for p in self.people:
                if not p.fleeing:
                    for sx, sy in scared_pos:
                        if math.hypot(p.x - sx, p.y - sy) < PANIC_RADIUS:
                            p.fleeing = True
                            break

        # ④ apply flee: override direction and speed
        for p in self.people:
            if p.fleeing and p.state not in ("climb", "fall", "jump"):
                if p.state in ("sit", "idle", "wave", "crouch"):
                    p.timer = 0
                p.state  = "run"
                p.facing = -1 if pred.x > p.x else 1
                p.vx     = p.facing * p.genome.walk_speed * p.genome.run_mult

        # ⑤ kill detection — iterate a copy to allow list mutation
        catch_r = pred.catch_radius()
        for p in list(self.people):
            if math.hypot(p.x - pred.x, p.y - pred.y) < catch_r:
                self.kill_effects.append(KillEffect(x=p.x, y=p.y))
                self.people.remove(p)
                pred.on_kill()
                self._spawn_replacement(pred)

    def _spawn_replacement(self, pred):
        if len(self.people) < 2:
            return
        far = sorted(self.people, key=lambda p: abs(p.x - pred.x), reverse=True)
        a, b = random.sample(far[:max(2, len(far)//2)], 2)
        child_genome = Genome.crossover(a.genome, b.genome)
        child = Person(self.sw, self.sh, child_genome)
        # spawn on the far side of the screen from predator
        far_x = pred.x + self.sw * 0.5
        child.x = max(child_genome.scale * 2,
                      min(self.sw - child_genome.scale * 2, far_x % self.sw))
        child.y = child.floor_y = float(self.sh) - child_genome.scale * 0.3
        self.people.append(child)

    # ── evolutionary step ─────────────────────────────────────────────────────
    def _evolve(self):
        self.generation += 1
        n = len(self.people)
        if n == 0:
            return

        # social bonus folded into fitness before ranking
        for p in self.people:
            p.genome.fitness += p.social_count * 2.0

        ranked = sorted(self.people, key=lambda p: p.genome.fitness, reverse=True)
        avg_f  = sum(p.genome.fitness for p in ranked) / n
        top    = ranked[0]
        print(f"Gen {self.generation:4d} | avg fit={avg_f:5.1f} | "
              f"best: spd={top.genome.walk_speed:.2f} scale={top.genome.scale:.0f} "
              f"climb={top.genome.climb_prob:.4f} social={top.social_count}")

        n_keep  = max(2, n // 2)
        parents = ranked[:n_keep]

        # weighted selection (sexual selection: social individuals preferred)
        weights = [max(0.01, p.genome.fitness) for p in parents]

        # replace losers' genomes in-place — position and state stay intact,
        # so no one teleports when the generation ticks over
        for loser in ranked[n_keep:]:
            a = random.choices(parents, weights=weights)[0]
            if random.random() < 0.72:
                a_island = int(a.floor_y) // 50
                same = [p for p in parents if int(p.floor_y)//50 == a_island and p is not a]
                b_pool = same if same else parents
            else:
                b_pool = parents
            b_candidates = [p for p in b_pool if p is not a]
            if not b_candidates:
                b_candidates = [p for p in parents if p is not a]
            b = random.choice(b_candidates)
            loser.genome = Genome.crossover(a.genome, b.genome)

        # reset fitness and social tally for the next generation
        for p in self.people:
            p.genome.fitness = 0.0
            p.social_count = 0

    # ── window change reactions ───────────────────────────────────────────────
    def react_to_windows(self, old_wins, new_wins):
        gone = {(wx, wy, ww) for (wx, wy, ww, wh) in old_wins} \
             - {(wx, wy, ww) for (wx, wy, ww, wh) in new_wins}
        if not gone:
            return
        for p in self.people:
            if p.state in ("fall", "jump"):
                continue
            for (wx, wy, ww) in gone:
                if abs(p.floor_y - wy) < 10 and wx - 20 < p.x < wx + ww + 20:
                    if p.state in ("sit", "idle", "wave", "crouch", "climb"):
                        p.timer = 0
                    p.state  = "jump"
                    p.vy     = -random.uniform(5.0, 9.0)
                    p.vx     = random.choice([-1, 1]) * p.genome.walk_speed * p.genome.run_mult
                    p.facing = 1 if p.vx > 0 else -1
                    break

    # ── stats string ──────────────────────────────────────────────────────────
    def stats(self):
        n = len(self.people)
        if n == 0:
            return ""
        avg_spd   = sum(p.genome.walk_speed for p in self.people) / n
        avg_scale = sum(p.genome.scale      for p in self.people) / n
        avg_climb = sum(p.genome.climb_prob for p in self.people) / n
        ticks_left = self.evolve_every - (self.tick_n % self.evolve_every)
        s = (f"gen {self.generation}  |  "
             f"spd {avg_spd:.1f}  scale {avg_scale:.0f}  climb {avg_climb:.3f}  |  "
             f"evo in {ticks_left // 30}s")
        if self.predator:
            s += f"  |  predator: {self.predator.kills} kills  spd {self.predator.speed:.1f}"
        return s


# ── GTK overlay ───────────────────────────────────────────────────────────────
class ShadowMen(Gtk.Window):
    def __init__(self, count, *, use_predator=False, evolve_every=EVOLVE_EVERY):
        super().__init__(type=Gtk.WindowType.POPUP)

        scr  = self.get_screen()
        disp = Gdk.Display.get_default()
        mon  = disp.get_primary_monitor() or disp.get_monitor(0)
        geo  = mon.get_geometry()
        self.sw, self.sh = geo.width, geo.height

        visual = scr.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        else:
            print("Warning: no RGBA visual — enable a compositor for transparency.")

        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.resize(self.sw, self.sh)
        self.move(0, 0)
        self.input_shape_combine_region(cairo.Region())

        area = Gtk.DrawingArea()
        area.connect("draw", self._on_draw)
        self.add(area)
        self.area = area

        self.colony    = Colony(count, self.sw, self.sh,
                                use_predator=use_predator,
                                evolve_every=evolve_every)
        self.win_cache = []
        self._win_tick = 0

        GLib.timeout_add(33, self._tick)
        self.show_all()

    def _tick(self):
        self._win_tick += 1
        if self._win_tick >= 30:
            old = self.win_cache
            self.win_cache = get_windows(self.sw, self.sh)
            self._win_tick = 0
            if self.win_cache != old:
                self.colony.react_to_windows(old, self.win_cache)
        self.colony.tick(self.win_cache)
        self.area.queue_draw()
        return True

    def _on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        for p in self.colony.people:
            p.draw(cr)

        # fading red splats where kills happened
        for ke in self.colony.kill_effects:
            ratio  = ke.age / ke.max_age
            alpha  = 0.75 * (1.0 - ratio)
            radius = 8 + ratio * 22
            cr.set_source_rgba(0.95, 0.06, 0.02, alpha)
            cr.arc(ke.x, ke.y, radius, 0, 2 * math.pi)
            cr.fill()

        if self.colony.predator:
            self.colony.predator.draw(cr)

        # stats line, bottom-left
        stats = self.colony.stats()
        if stats:
            cr.set_font_size(11)
            cr.select_font_face("monospace",
                                cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_source_rgba(0, 0, 0, 0.6)
            cr.move_to(11, self.sh - 9)
            cr.show_text(stats)
            cr.set_source_rgba(1, 1, 0.8, 0.55)
            cr.move_to(10, self.sh - 10)
            cr.show_text(stats)

        return False


# ── autostart ─────────────────────────────────────────────────────────────────
def install_autostart(script_path):
    d = Path.home() / ".config" / "autostart"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "shadowmen.desktop"
    f.write_text(f"""[Desktop Entry]
Type=Application
Name=Shadow Men
Comment=Evolving shadow people desktop widget
Exec=python3 {script_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
""")
    print(f"Autostart installed → {f}")


# ── entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Evolving shadow people")
    ap.add_argument("--count",    type=int,   default=8,
                    help="population size (default 8)")
    ap.add_argument("--predator", action="store_true",
                    help="spawn a red predator that hunts the colony")
    ap.add_argument("--evo-speed", type=float, default=1.0, metavar="N",
                    help="run evolution N× faster (e.g. 3 = every ~7s)")
    ap.add_argument("--install-autostart", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="wipe saved population")
    args = ap.parse_args()

    if args.install_autostart:
        install_autostart(Path(__file__).resolve())
        return

    if args.reset and SAVE_FILE.exists():
        SAVE_FILE.unlink()
        print("Population wiped — starting from scratch.")

    evolve_every = max(1, int(EVOLVE_EVERY / args.evo_speed))

    print(f"Starting {args.count} souls | "
          f"predator={'yes' if args.predator else 'no'} | "
          f"evo every {evolve_every//30}s")

    app = ShadowMen(args.count,
                    use_predator=args.predator,
                    evolve_every=evolve_every)

    def _quit(*_):
        app.colony.save()
        print(f"\nSaved gen {app.colony.generation} → {SAVE_FILE}")
        Gtk.main_quit()

    signal.signal(signal.SIGINT,  _quit)
    signal.signal(signal.SIGTERM, _quit)
    GLib.timeout_add(200, lambda: True)  # keep Python's GIL ticking so SIGINT is delivered

    Gtk.main()


if __name__ == "__main__":
    main()
