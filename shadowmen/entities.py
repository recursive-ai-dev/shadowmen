from __future__ import annotations
import json
import logging
import math
import random
from dataclasses import dataclass
from typing import List, Optional

from shadowmen.config import SAVE_FILE, SimConfig
from shadowmen.genome import Genome
from shadowmen.render import draw_fire, draw_person, draw_shelter
from shadowmen.utils import WindowSnapshot

try:
    import cairo
except ImportError:
    pass

log = logging.getLogger(__name__)

@dataclass
class KillEffect:
    x: float
    y: float
    age: int = 0
    max_age: int = 48

class Person:
    def __init__(
        self,
        sw: int,
        sh: int,
        genome: Genome | None = None,
        home_x: float | None = None,
        home_y: float | None = None,
    ) -> None:
        self.sw, self.sh = sw, sh
        self.genome = genome or Genome.random()
        s = self.genome.scale
        self.energy = 100.0  # New: Energy meter

        if home_x is not None and home_y is not None:
            self.x, self.y = home_x, home_y
            self.home_x, self.home_y = home_x, home_y
            self.has_shelter = True
        else:
            self.x = float(random.randint(int(s * 2), int(sw - s * 2)))
            self.y = float(sh - s * 0.3)
            self.home_x, self.home_y = None, None
            self.has_shelter = False

        self.floor_y = self.y
        self.vx = random.choice([-1, 1]) * self.genome.walk_speed
        self.vy = 0.0
        self.facing = 1 if self.vx > 0 else -1
        self.state = "walk"
        self.t = random.uniform(0, 400)
        self.timer = 0
        self.wall_x: float | None = None
        self.wall_side = 0
        self.social_count = 0
        self.fleeing = False
        self.fire_timer = 0
        self.fire_x, self.fire_y = 0.0, 0.0
        self.alarm_timer = 0 # Kin selection signaling

    def update(self, windows: List[WindowSnapshot]) -> None:
        self.t += 1
        self.genome.fitness += 0.004

        # Metabolism: Energy decay
        cost = self.genome.metabolism
        if self.state in ("run", "jump", "climb"): cost *= 2.0
        # Biome effects
        current_biome = "neutral"
        for win in windows:
            if abs(self.y - win.y) < 5 and win.x < self.x < win.x + win.w:
                current_biome = win.biome
                break

        if current_biome == "hardened": cost *= 1.5
        elif current_biome == "information-rich": self.energy += 0.05
        self.energy -= cost

        if self.energy <= 0:
            self.energy = 0
            self.state = "crouch" # Exhaustion
            self.vx = 0

        if self.alarm_timer > 0: self.alarm_timer -= 1
        if self.fire_timer > 0:
            self.fire_timer -= 1
            self.genome.fitness += 0.012

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
            # Grazing / Recovery
            if self.state in ("sit", "idle"): self.energy = min(100.0, self.energy + 0.1)
            if self.timer <= 0: self._resume_walk()

    def draw(self, cr: cairo.Context) -> None:
        g, s = self.genome, self.genome.scale
        if self.has_shelter and self.home_x is not None:
            draw_shelter(cr, self.home_x, self.home_y, s)
        if self.fire_timer > 0:
            draw_fire(cr, self.fire_x, self.fire_y, self.t, s)

        color = g.body_color()
        # Alarm glow
        if self.alarm_timer > 0:
            draw_person(cr, self.x, self.y, self.t, self.state, self.facing, s, g.leg_amp, g.arm_amp, color, glow=True, glow_color=(1, 1, 0, 0.8))

        draw_person(cr, self.x, self.y, self.t, self.state, self.facing, s, g.leg_amp, g.arm_amp, color)

    def _walk_step(self, windows: List[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x += self.vx
        if self.vx: self.facing = 1 if self.vx > 0 else -1
        self._check_screen_boundaries(s)
        self._check_window_edges(windows, s)
        floor = self._find_floor(windows)
        if self.y < floor - 3:
            self.state = "fall"
            self.vy = 0.0
            return
        self.y = self.floor_y = floor
        if not self.fleeing: self._choose_idle_behavior(self.genome)

    def _check_screen_boundaries(self, s: float) -> None:
        if self.x <= s:
            self.x, self.vx, self.facing = s, abs(self.vx), 1
        elif self.x >= self.sw - s:
            self.x, self.vx, self.facing = self.sw - s, -abs(self.vx), -1

    def _check_window_edges(self, windows: List[WindowSnapshot], s: float) -> bool:
        for win in windows:
            if abs(self.y - win.y) < 5 and win.x + 4 < self.x < win.x + win.w - 4:
                self.y = self.floor_y = float(win.y)
            elif abs(self.x - win.x) < s * 1.4 and win.y < self.y < win.y + win.h:
                if random.random() < self.genome.climb_prob:
                    self._begin_climb(float(win.x), self.facing)
                    return True
        return False

    def _choose_idle_behavior(self, g: Genome) -> None:
        r = random.random()
        if r < g.sit_prob: self._pause("sit", random.randint(100, 380))
        elif r < g.sit_prob + g.wave_prob: self._pause("wave", random.randint(80, 220))
        elif not self.has_shelter and r < g.sit_prob + g.wave_prob + g.shelter_skill:
            self.has_shelter, self.home_x, self.home_y = True, self.x, self.y
            self._pause("crouch", random.randint(200, 450))

    def _climb_step(self, windows: List[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.y -= 2.5
        if self.wall_x is not None: self.x = self.wall_x + (-self.wall_side) * s * 0.92
        for win in windows:
            if self.wall_x is not None:
                if (abs(self.wall_x - win.x) < 8 or abs(self.wall_x - (win.x + win.w)) < 8) and self.y <= win.y + s:
                    self.y = self.floor_y = float(win.y)
                    self.genome.fitness += 3.0
                    self._resume_walk(side=self.wall_side)
                    return
        if self.y < s * 1.5:
            self.state, self.vy, self.vx = "fall", -0.5, -self.wall_side * random.uniform(2.0, 4.5)

    def _fall_step(self, windows: List[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx * 0.55))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy, self.state = 0.0, "walk"
            self.facing = 1 if self.vx > 0 else -1

    def _jump_step(self, windows: List[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y, self.floor_y, self.vy, self.state = floor, floor, 0.0, "run"

    def _find_floor(self, windows: List[WindowSnapshot]) -> float:
        g = float(self.sh) - self.genome.scale * 0.3
        for win in windows:
            if win.x + 4 < self.x < win.x + win.w - 4 and self.y <= win.y + 3:
                g = min(g, float(win.y))
        return g

    def _begin_climb(self, wall_x: float, side: int) -> None:
        self.state, self.wall_x, self.wall_side, self.facing, self.vx = "climb", wall_x, side, side, 0.0

    def _pause(self, state: str, ticks: int) -> None:
        self.state, self.timer, self.vx = state, ticks, 0.0

    def _resume_walk(self, side: int | None = None) -> None:
        self.state, self.wall_x = "walk", None
        spd = self.genome.walk_speed
        self.vx = (side * spd) if side is not None else (self.vx or random.choice([-1, 1]) * spd)
        self.facing = 1 if self.vx > 0 else -1

class Predator:
    SCALE = 22.0
    def __init__(self, sw: int, sh: int, config: SimConfig) -> None:
        self.config, self.sw, self.sh = config, sw, sh
        self.x, self.y = float(sw // 2), float(sh - self.SCALE * 0.3)
        self.speed, self.vx, self.vy, self.facing, self.state, self.t, self.kills = config.pred_base_speed, config.pred_base_speed, 0.0, 1, "run", 0.0, 0

    def update(self, people: List[Person], windows: List[WindowSnapshot]) -> None:
        self.t += 1
        if people:
            target = min(people, key=lambda p: abs(p.x - self.x))
            self.vx = math.copysign(self.speed, target.x - self.x)
        self.x = max(self.SCALE, min(self.sw - self.SCALE, self.x + self.vx))
        self.facing = 1 if self.vx >= 0 else -1
        floor = float(self.sh) - self.SCALE * 0.3
        self.vy += 0.65
        self.y = min(self.y + self.vy, floor)
        if self.y >= floor: self.vy = self.y = self.floor_y = 0.0 or floor # logic fix

    def catch_radius(self) -> float: return self.SCALE * 0.85
    def on_kill(self) -> None:
        self.kills += 1
        self.speed = min(self.config.pred_speed_cap, self.speed + self.config.pred_speed_inc)

    def draw(self, cr: cairo.Context) -> None:
        draw_person(cr, self.x, self.y, self.t, self.state, self.facing, self.SCALE, 0.5, 0.42, (0.68, 0.08, 0.02, 0.95), glow=True, glow_color=(1, 0.3, 0.04, 0.62))

class Colony:
    def __init__(self, count: int, sw: int, sh: int, *, config: SimConfig) -> None:
        self.config, self.count, self.sw, self.sh, self.tick_n, self.generation, self.kill_effects = config, count, sw, sh, 0, 0, []
        self.predator = Predator(sw, sh, config) if config.use_predator else None
        self.people = self._load_or_init()

    def _load_or_init(self) -> List[Person]:
        if SAVE_FILE.exists():
            try:
                data = json.loads(SAVE_FILE.read_text())
                self.generation = int(data.get("generation", 0))
                people = [Person(self.sw, self.sh, Genome.from_dict(d["genome"]), d.get("home_x"), d.get("home_y")) for d in data.get("people", [])]
                while len(people) < self.count: people.append(Person(self.sw, self.sh))
                return people[:self.count]
            except: pass
        return [Person(self.sw, self.sh) for _ in range(self.count)]

    def save(self) -> None:
        try:
            payload = json.dumps({"generation": self.generation, "people": [{"genome": p.genome.to_dict(), "home_x": p.home_x, "home_y": p.home_y, "has_shelter": p.has_shelter} for p in self.people]}, indent=2)
            SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SAVE_FILE.write_text(payload)
        except: pass

    def tick(self, windows: List[WindowSnapshot]) -> None:
        self.tick_n += 1
        for p in self.people: p.update(windows)
        self._handle_interactions()
        if self.predator: self._handle_predator(windows)
        for ke in self.kill_effects: ke.age += 1
        self.kill_effects = [ke for ke in self.kill_effects if ke.age < ke.max_age]
        if self.tick_n % self.config.evolve_every == 0: self._evolve(); self.save()

    def _handle_interactions(self) -> None:
        # Kin selection: sharing energy or alarm calls
        for i, a in enumerate(self.people):
            for b in self.people[i+1:]:
                dist = abs(a.x - b.x)
                if dist < 50:
                    # Energy sharing
                    if a.energy > 60 and b.energy < 30:
                        amt = 10 * a.genome.altruism
                        a.energy -= amt; b.energy += amt
                        a.genome.fitness += 0.5

    def _handle_predator(self, windows: List[WindowSnapshot]) -> None:
        pred = self.predator
        if not pred: return
        pred.update(self.people, windows)

        # Alarm calls (Kin Selection)
        for p in self.people:
            p.fleeing = False
            if abs(p.x - pred.x) < self.config.flee_radius_x:
                p.fleeing = True
                if random.random() < p.genome.altruism and p.alarm_timer <= 0:
                    p.alarm_timer = 60 # Signal for 2 seconds
                    # Alert nearby kin
                    for kin in self.people:
                        if kin is not p and abs(kin.x - p.x) < 300:
                            kin.fleeing = True

        for p in self.people:
            if p.fleeing and p.state not in ("climb", "fall", "jump"):
                p.state, p.vx = "run", (-1 if pred.x > p.x else 1) * p.genome.walk_speed * p.genome.run_mult

        catch_r = pred.catch_radius()
        for p in list(self.people):
            if math.hypot(p.x - pred.x, p.y - pred.y) < catch_r:
                self.kill_effects.append(KillEffect(p.x, p.y))
                self.people.remove(p)
                pred.on_kill()
                self._spawn_replacement(pred)

    def _spawn_replacement(self, pred: Predator) -> None:
        if len(self.people) < 2: self.people.append(Person(self.sw, self.sh)); return
        far = sorted(self.people, key=lambda p: abs(p.x - pred.x), reverse=True)
        a, b = random.sample(far[:max(2, len(far)//2)], 2)
        child = Person(self.sw, self.sh, Genome.crossover(a.genome, b.genome), a.home_x, a.home_y)
        self.people.append(child)

    def _evolve(self) -> None:
        self.generation += 1
        if not self.people: return
        ranked = sorted(self.people, key=lambda p: p.genome.fitness, reverse=True)
        parents = ranked[:max(2, len(self.people)//2)]
        for loser in ranked[len(parents):]:
            a, b = random.sample(parents, 2)
            loser.genome = Genome.crossover(a.genome, b.genome)
            loser.energy = 100.0
            loser.state = "walk"
        for p in self.people: p.genome.fitness = 0

    def react_to_windows(self, old_wins, new_wins) -> None:
        gone = {w.id for w in old_wins} - {w.id for w in new_wins}
        for p in self.people:
            for win in old_wins:
                if win.id in gone and abs(p.floor_y - win.y) < 10 and win.x < p.x < win.x + win.w:
                    p.state, p.vy = "jump", -random.uniform(5, 9)

    def stats(self) -> str:
        if not self.people: return "extinct"
        avg_e = sum(p.energy for p in self.people) / len(self.people)
        return f"gen {self.generation} | energy {avg_e:.1f}"
