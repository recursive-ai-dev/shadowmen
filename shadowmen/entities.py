from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass

from shadowmen.config import SAVE_FILE, SimConfig
from shadowmen.genome import Genome
from shadowmen.render import draw_fire, draw_person, draw_shelter

try:
    import cairo
except ImportError:
    pass

log = logging.getLogger(__name__)


@dataclass
class KillEffect:
    """A short-lived radial splat drawn at the point where a person was caught."""

    x: float
    y: float
    age: int = 0
    max_age: int = 48


class Person:
    """A single shadow-person agent with a genome, position, and behavioural state."""

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

        if home_x is not None and home_y is not None:
            self.x = home_x
            self.y = home_y
            self.home_x = home_x
            self.home_y = home_y
            self.has_shelter = True
        else:
            self.x = float(random.randint(int(s * 2), int(sw - s * 2)))
            self.y = float(sh - s * 0.3)
            self.home_x = None
            self.home_y = None
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
        self.fire_x = 0.0
        self.fire_y = 0.0

    def update(self, windows: list[tuple[int, int, int, int]]) -> None:
        self.t += 1
        self.genome.fitness += 0.004

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
            if self.timer <= 0:
                self._resume_walk()

    def draw(self, cr: cairo.Context) -> None:
        g = self.genome
        s = g.scale
        
        if self.has_shelter and self.home_x is not None and self.home_y is not None:
            draw_shelter(cr, self.home_x, self.home_y, s)

        if self.fire_timer > 0:
            draw_fire(cr, self.fire_x, self.fire_y, self.t, s)

        color = g.body_color()
        args = (
            cr,
            self.x,
            self.y,
            self.t,
            self.state,
            self.facing,
            s,
            g.leg_amp,
            g.arm_amp,
            color,
        )
        draw_person(*args, glow=True)
        draw_person(*args, glow=False)

    def _walk_step(self, windows: list[tuple[int, int, int, int]]) -> None:
        g, s = self.genome, self.genome.scale
        self.x += self.vx
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

        if self._check_screen_boundaries(s):
            return
        if self._check_window_edges(windows, s):
            return

        floor = self._find_floor(windows)
        if self.y < floor - 3:
            self.state = "fall"
            self.vy = 0.0
            return
        self.y = self.floor_y = floor

        if not self.fleeing:
            self._choose_idle_behavior(g)

    def _check_screen_boundaries(self, s: float) -> bool:
        if self.x <= s:
            self.x = s
            self.vx = abs(self.vx)
            self.facing = 1
        elif self.x >= self.sw - s:
            self.x = self.sw - s
            self.vx = -abs(self.vx)
            self.facing = -1
        return False

    def _check_window_edges(self, windows: list[tuple[int, int, int, int]], s: float) -> bool:
        g = self.genome
        for wx, wy, ww, wh in windows:
            if abs(self.y - wy) < 5 and wx + 4 < self.x < wx + ww - 4:
                self.y = self.floor_y = float(wy)
            elif abs(self.x - wx) < s * 1.4 and wy < self.y < wy + wh:
                if random.random() < g.climb_prob:
                    self._begin_climb(float(wx), self.facing)
                    return True
            elif abs(self.x - (wx + ww)) < s * 1.4 and wy < self.y < wy + wh:
                if random.random() < g.climb_prob:
                    self._begin_climb(float(wx + ww), self.facing)
                    return True
        return False

    def _choose_idle_behavior(self, g: Genome) -> None:
        r = random.random()
        cumulative = g.sit_prob
        if r < cumulative:
            self._pause("sit", random.randint(100, 380))
            return
        
        cumulative += g.wave_prob
        if r < cumulative:
            self._pause("wave", random.randint(80, 220))
            return

        cumulative += g.shelter_skill
        if not self.has_shelter and r < cumulative:
            self.has_shelter = True
            self.home_x, self.home_y = self.x, self.y
            self._pause("crouch", random.randint(200, 450))
            log.info("A shadow-person built a shelter at (%.1f, %.1f)", self.x, self.y)
            return

        cumulative += g.fire_skill
        if self.fire_timer <= 0 and r < cumulative:
            self.fire_timer = random.randint(600, 1800)
            self.fire_x, self.fire_y = self.x, self.y
            self._pause("crouch", random.randint(100, 250))
            log.info("A shadow-person started a fire at (%.1f, %.1f)", self.x, self.y)
            return

        cumulative += g.run_prob
        if r < cumulative:
            if self.state == "walk":
                self.state = "run"
                self.vx = math.copysign(g.walk_speed * g.run_mult, self.vx)
            elif random.random() < 0.35:
                self.state = "jump"
                self.vy = -random.uniform(8.0, 11.5)
            else:
                self.state = "walk"
                self.vx = math.copysign(g.walk_speed, self.vx)
            return

        if r < cumulative + 0.0014:
            if self.state == "walk":
                self._pause("crouch", random.randint(35, 75))

    def _climb_step(self, windows: list[tuple[int, int, int, int]]) -> None:
        g, s = self.genome, self.genome.scale
        self.y -= 2.5
        if self.wall_x is not None:
            self.x = self.wall_x + (-self.wall_side) * s * 0.92

        for wx, wy, ww, _ in windows:
            if self.wall_x is not None:
                near = abs(self.wall_x - wx) < 8 or abs(self.wall_x - (wx + ww)) < 8
                if near and self.y <= wy + s:
                    self.y = self.floor_y = float(wy)
                    self.genome.fitness += 3.0
                    self._resume_walk(side=self.wall_side)
                    return

        if self.y < g.scale * 1.5:
            self.state = "fall"
            self.vy = -0.5
            self.vx = -self.wall_side * random.uniform(2.0, 4.5)

    def _fall_step(self, windows: list[tuple[int, int, int, int]]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx * 0.55))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy = 0.0
            self.genome.fitness -= 0.8
            if not self.vx:
                self.vx = random.choice([-1, 1]) * self.genome.walk_speed
            self.state = "walk"
            self.facing = 1 if self.vx > 0 else -1

    def _jump_step(self, windows: list[tuple[int, int, int, int]]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy = 0.0
            self.state = "run"
            self.facing = 1 if self.vx > 0 else -1

    def _find_floor(self, windows: list[tuple[int, int, int, int]]) -> float:
        g = float(self.sh) - self.genome.scale * 0.3
        for wx, wy, ww, _ in windows:
            if wx + 4 < self.x < wx + ww - 4 and self.y <= wy + 3:
                g = min(g, float(wy))
        return g

    def _begin_climb(self, wall_x: float, side: int) -> None:
        self.state = "climb"
        self.wall_x = wall_x
        self.wall_side = side
        self.facing = side
        self.vx = 0.0

    def _pause(self, state: str, ticks: int) -> None:
        self.state = state
        self.timer = ticks
        self.vx = 0.0

    def _resume_walk(self, side: int | None = None) -> None:
        self.state = "walk"
        self.wall_x = None
        spd = self.genome.walk_speed
        self.vx = (side * spd) if side is not None else (self.vx or random.choice([-1, 1]) * spd)
        self.facing = 1 if self.vx > 0 else -1


class Predator:
    """Red shadow that hunts colony members and grows faster with each kill."""

    SCALE = 22.0

    def __init__(self, sw: int, sh: int, config: SimConfig) -> None:
        self.config = config
        self.sw, self.sh = sw, sh
        self.x = float(sw // 2)
        self.y = float(sh - self.SCALE * 0.3)
        self.floor_y = self.y
        self.speed = config.pred_base_speed
        self.vx = config.pred_base_speed
        self.vy = 0.0
        self.facing = 1
        self.t = 0
        self.kills = 0
        self.state = "run"

    def update(
        self,
        people: list[Person],
        windows: list[tuple[int, int, int, int]],
    ) -> None:
        self.t += 1
        s = self.SCALE

        floor_people = [
            p
            for p in people
            if abs(p.floor_y - self.floor_y) < self.config.flee_radius_y
            and p.state not in ("fall",)
        ]
        if floor_people:
            target = min(floor_people, key=lambda p: abs(p.x - self.x))
            self.vx = math.copysign(self.speed, target.x - self.x)
        else:
            if self.x <= s:
                self.vx = self.speed
                self.facing = 1
            elif self.x >= self.sw - s:
                self.vx = -self.speed
                self.facing = -1

        self.x = max(s, min(self.sw - s, self.x + self.vx))
        self.facing = 1 if self.vx >= 0 else -1

        floor = float(self.sh) - s * 0.3
        self.vy += 0.65
        self.y = min(self.y + self.vy, floor)
        if self.y >= floor:
            self.vy = 0.0
            self.y = self.floor_y = floor

        self.state = "run"

    def catch_radius(self) -> float:
        return self.SCALE * 0.85

    def on_kill(self) -> None:
        self.kills += 1
        self.speed = min(self.config.pred_speed_cap, self.speed + self.config.pred_speed_inc)
        log.info("kill #%d! predator speed → %.2f", self.kills, self.speed)

    def draw(self, cr: cairo.Context) -> None:
        pred_body: tuple[float, float, float, float] = (0.68, 0.08, 0.02, 0.95)
        pred_glow: tuple[float, float, float, float] = (1.00, 0.30, 0.04, 0.62)
        args = (
            cr,
            self.x,
            self.y,
            self.t,
            self.state,
            self.facing,
            self.SCALE,
            0.50,
            0.42,
            pred_body,
        )
        draw_person(*args, glow=True, glow_color=pred_glow)
        draw_person(*args, glow=False)


class Colony:
    def __init__(
        self,
        count: int,
        sw: int,
        sh: int,
        *,
        config: SimConfig,
    ) -> None:
        self.config = config
        self.count = count
        self.sw, self.sh = sw, sh
        self.tick_n = 0
        self.generation = 0
        self.kill_effects: list[KillEffect] = []
        self.predator = Predator(sw, sh, config) if config.use_predator else None
        self.people = self._load_or_init()

    def _load_or_init(self) -> list[Person]:
        if SAVE_FILE.exists():
            try:
                data = json.loads(SAVE_FILE.read_text())
                self.generation = int(data.get("generation", 0))
                
                people_data = data.get("people", [])
                if not people_data and "genomes" in data:
                    # Backward compatibility for old save format
                    genomes = [Genome.from_dict(d) for d in data["genomes"]]
                    while len(genomes) < self.count:
                        genomes.append(Genome.random())
                    genomes = genomes[: self.count]
                    log.info(
                        "Loaded legacy generation %d (%d souls)", self.generation, len(genomes)
                    )
                    return [Person(self.sw, self.sh, g) for g in genomes]

                people = []
                for d in people_data:
                    g = Genome.from_dict(d["genome"])
                    hx = d.get("home_x")
                    hy = d.get("home_y")
                    p = Person(self.sw, self.sh, g, home_x=hx, home_y=hy)
                    p.has_shelter = d.get("has_shelter", False)
                    people.append(p)
                
                while len(people) < self.count:
                    people.append(Person(self.sw, self.sh))
                
                people = people[: self.count]
                log.info("Loaded generation %d (%d souls)", self.generation, len(people))
                return people
            except Exception as e:
                log.warning("Save file unreadable (%s), starting fresh.", e)
        return [Person(self.sw, self.sh) for _ in range(self.count)]

    def save(self) -> None:
        payload = json.dumps(
            {
                "generation": self.generation,
                "people": [
                    {
                        "genome": p.genome.to_dict(),
                        "home_x": p.home_x,
                        "home_y": p.home_y,
                        "has_shelter": p.has_shelter,
                    }
                    for p in self.people
                ],
            },
            indent=2,
        )
        try:
            SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SAVE_FILE.write_text(payload)
        except OSError as e:
            log.error("Failed to save population to %s: %s", SAVE_FILE, e)

    def tick(self, windows: list[tuple[int, int, int, int]]) -> None:
        self.tick_n += 1

        for p in self.people:
            p.update(windows)

        self._handle_interactions()

        if self.predator:
            self._handle_predator(windows)

        for ke in self.kill_effects:
            ke.age += 1
        self.kill_effects = [ke for ke in self.kill_effects if ke.age < ke.max_age]

        if self.tick_n % self.config.evolve_every == 0:
            self._evolve()
            self.save()

    def _handle_interactions(self) -> None:
        people = self.people
        for i in range(len(people)):
            a = people[i]
            for j in range(i + 1, len(people)):
                b = people[j]
                if abs(a.y - b.y) > max(a.genome.scale, b.genome.scale) * 1.5:
                    continue
                threshold = (
                    (a.genome.social_r + b.genome.social_r)
                    * 0.5
                    * (a.genome.scale + b.genome.scale)
                    * 0.5
                )
                dist = abs(a.x - b.x)

                if dist < threshold:
                    if (
                        not a.fleeing
                        and not b.fleeing
                        and a.state in ("walk", "idle")
                        and b.state in ("walk", "idle")
                        and random.random() < 0.006
                    ):
                        a.facing = 1 if b.x > a.x else -1
                        b.facing = 1 if a.x > b.x else -1
                        a._pause("wave", random.randint(60, 130))
                        b._pause("wave", random.randint(60, 130))
                        a.genome.fitness += 0.6
                        a.social_count += 1
                        b.genome.fitness += 0.6
                        b.social_count += 1

                    elif (
                        a.state == "walk"
                        and b.state == "walk"
                        and dist < (a.genome.scale + b.genome.scale) * 0.7
                    ):
                        into = (a.x < b.x and a.vx > 0 and b.vx < 0) or (
                            a.x > b.x and a.vx < 0 and b.vx > 0
                        )
                        if into:
                            a.vx, b.vx = -a.vx, -b.vx
                            a.facing = 1 if a.vx > 0 else -1
                            b.facing = 1 if b.vx > 0 else -1

    def _handle_predator(self, windows: list[tuple[int, int, int, int]]) -> None:
        pred = self.predator
        if not pred:
            return
        pred.update(self.people, windows)
        self._update_flee_flags(pred)
        self._apply_flee_behavior(pred)
        self._check_kill_collisions(pred)

    def _update_flee_flags(self, pred: Predator) -> None:
        for p in self.people:
            p.fleeing = False

        for p in self.people:
            if (
                abs(p.x - pred.x) < self.config.flee_radius_x
                and abs(p.floor_y - pred.floor_y) < self.config.flee_radius_y
            ):
                p.fleeing = True

        scared_pos = [(p.x, p.y) for p in self.people if p.fleeing]
        if scared_pos:
            for p in self.people:
                if not p.fleeing:
                    for sx, sy in scared_pos:
                        if math.hypot(p.x - sx, p.y - sy) < self.config.panic_radius:
                            p.fleeing = True
                            break

    def _apply_flee_behavior(self, pred: Predator) -> None:
        for p in self.people:
            if p.fleeing and p.state not in ("climb", "fall", "jump"):
                if p.state in ("sit", "idle", "wave", "crouch"):
                    p.timer = 0
                p.state = "run"
                p.facing = -1 if pred.x > p.x else 1
                p.vx = p.facing * p.genome.walk_speed * p.genome.run_mult

    def _check_kill_collisions(self, pred: Predator) -> None:
        catch_r = pred.catch_radius()
        for p in list(self.people):
            if math.hypot(p.x - pred.x, p.y - pred.y) < catch_r:
                self.kill_effects.append(
                    KillEffect(x=p.x, y=p.y, max_age=self.config.kill_effect_ticks)
                )
                self.people.remove(p)
                pred.on_kill()
                self._spawn_replacement(pred)

    def _spawn_replacement(self, pred: Predator) -> None:
        far_x = pred.x + self.sw * 0.5
        if len(self.people) < 2:
            child = Person(self.sw, self.sh)
            child.x = max(
                child.genome.scale * 2, min(self.sw - child.genome.scale * 2, far_x % self.sw)
            )
            child.y = child.floor_y = float(self.sh) - child.genome.scale * 0.3
            self.people.append(child)
            log.info("Colony critically low — spawned a random newcomer.")
            return
        far = sorted(self.people, key=lambda p: abs(p.x - pred.x), reverse=True)
        a, b = random.sample(far[: max(2, len(far) // 2)], 2)
        child_genome = Genome.crossover(a.genome, b.genome)

        # Use parent a's home if it exists
        hx, hy = a.home_x, a.home_y
        child = Person(self.sw, self.sh, child_genome, home_x=hx, home_y=hy)

        if hx is None:
            child.x = max(
                child_genome.scale * 2, min(self.sw - child_genome.scale * 2, far_x % self.sw)
            )
            child.y = child.floor_y = float(self.sh) - child.genome.scale * 0.3

        self.people.append(child)


    def _evolve(self) -> None:
        self.generation += 1
        n = len(self.people)
        if n == 0:
            return

        for p in self.people:
            p.genome.fitness += p.social_count * 2.0

        ranked = sorted(self.people, key=lambda p: p.genome.fitness, reverse=True)
        avg_f = sum(p.genome.fitness for p in ranked) / n
        top = ranked[0]
        log.info(
            "Gen %4d | avg fit=%5.1f | best: spd=%.2f scale=%.0f climb=%.4f social=%d",
            self.generation,
            avg_f,
            top.genome.walk_speed,
            top.genome.scale,
            top.genome.climb_prob,
            top.social_count,
        )

        n_keep = max(2, n // 2)
        parents = ranked[:n_keep]
        weights = [max(0.01, p.genome.fitness) for p in parents]

        for loser in ranked[n_keep:]:
            a = random.choices(parents, weights=weights)[0]
            if random.random() < 0.72:
                a_island = int(a.floor_y) // 50
                same = [p for p in parents if int(p.floor_y) // 50 == a_island and p is not a]
                b_pool = same if same else parents
            else:
                b_pool = parents
            b_candidates = [p for p in b_pool if p is not a]
            if not b_candidates:
                b_candidates = [p for p in parents if p is not a]
            b = random.choice(b_candidates)
            loser.genome = Genome.crossover(a.genome, b.genome)
            loser.home_x, loser.home_y = a.home_x, a.home_y
            loser.has_shelter = a.has_shelter
            loser.fire_timer = 0
            loser.state = "walk"
            loser.timer = 0
            loser.wall_x = None
            loser.vx = random.choice([-1, 1]) * loser.genome.walk_speed
            loser.vy = 0.0
            
            if loser.home_x is not None:
                loser.x, loser.y = loser.home_x, loser.home_y
                loser.floor_y = loser.y

        for p in self.people:
            p.genome.fitness = 0.0
            p.social_count = 0

    def react_to_windows(
        self,
        old_wins: list[tuple[int, int, int, int]],
        new_wins: list[tuple[int, int, int, int]],
    ) -> None:
        gone = {(wx, wy, ww) for (wx, wy, ww, wh) in old_wins} - {
            (wx, wy, ww) for (wx, wy, ww, wh) in new_wins
        }
        if not gone:
            return
        for p in self.people:
            if p.state in ("fall", "jump"):
                continue
            for wx, wy, ww in gone:
                if abs(p.floor_y - wy) < 10 and wx - 20 < p.x < wx + ww + 20:
                    if p.state in ("sit", "idle", "wave", "crouch", "climb"):
                        p.timer = 0
                    p.state = "jump"
                    p.vy = -random.uniform(5.0, 9.0)
                    p.vx = random.choice([-1, 1]) * p.genome.walk_speed * p.genome.run_mult
                    p.facing = 1 if p.vx > 0 else -1
                    break

    def stats(self) -> str:
        n = len(self.people)
        if n == 0:
            return "colony extinct — run with --reset to start fresh"
        avg_spd = sum(p.genome.walk_speed for p in self.people) / n
        avg_scale = sum(p.genome.scale for p in self.people) / n
        avg_climb = sum(p.genome.climb_prob for p in self.people) / n
        ticks_left = self.config.evolve_every - (self.tick_n % self.config.evolve_every)
        s = (
            f"gen {self.generation}  |  "
            f"spd {avg_spd:.1f}  scale {avg_scale:.0f}  climb {avg_climb:.3f}  |  "
            f"evo in {ticks_left // 30}s"
        )
        if self.predator:
            s += f"  |  predator: {self.predator.kills} kills  spd {self.predator.speed:.1f}"
        return s
