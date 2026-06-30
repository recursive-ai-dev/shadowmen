from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass

from shadowmen.config import SAVE_FILE, SimConfig
from shadowmen.genome import Genome, PredatorGenome
from shadowmen.render import draw_fire, draw_person, draw_shelter
from shadowmen.utils import SpatialHash, WindowSnapshot

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
    """An evolving agent that interacts with the desktop environment and other agents."""

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
        self.energy = 100.0

        if home_x is not None and home_y is not None:
            self.x, self.y = home_x, home_y
            self.home_x: float | None = home_x
            self.home_y: float | None = home_y
            self.has_shelter = True
        else:
            self.x = float(random.randint(int(s * 2), max(int(s * 2), int(sw - s * 2))))
            self.y = float(sh - s * 0.3)
            self.home_x = None
            self.home_y = None
            self.has_shelter = False

        self.floor_y = self.y
        self.satiation_timer = 0
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
        self.alarm_timer = 0  # Kin selection signaling
        self.age = 0
        self.max_age = random.randint(3000, 6000)

    def update(self, windows: list[WindowSnapshot]) -> None:
        self.t += 1
        self.genome.fitness += 0.004

        # Advanced Metabolism: scale * (1 + metabolism * v^2)
        vel_sq = self.vx**2 + self.vy**2
        cost = (self.genome.scale / 18.0) * (
            1.0 + self.genome.metabolism * vel_sq * 0.5
        )

        # Biome effects
        current_biome = "neutral"
        for win in windows:
            if abs(self.y - win.y) < 5 and win.x < self.x < win.x + win.w:
                current_biome = win.biome
                break

        if current_biome == "hardened":
            cost *= 1.4
        elif current_biome == "information-rich":
            self.energy = min(100.0, self.energy + 0.08)

        self.energy -= cost * 0.05  # Normalization

        if self.energy <= 0:
            self.energy = 0
            if self.state != "crouch":
                self._pause("crouch", random.randint(100, 300))  # Exhaustion
            self.vx = 0

        if self.alarm_timer > 0:
            self.alarm_timer -= 1
        if self.fire_timer > 0:
            self.fire_timer -= 1
            self.genome.fitness += 0.012

        if self.state in ("walk", "run"):
            self._walk_step(windows)
            # Satiety-based behavior: rest if energy is low
            if self.energy < 20.0 and not self.fleeing:
                if self.has_shelter and self.home_x is not None:
                    if abs(self.x - self.home_x) > 10:
                        self.state = "walk"
                        self.vx = math.copysign(
                            self.genome.walk_speed, self.home_x - self.x
                        )
                    else:
                        self._pause(
                            random.choice(["sit", "idle"]), random.randint(150, 400)
                        )
                else:
                    self._pause(
                        random.choice(["sit", "idle"]), random.randint(150, 400)
                    )
        elif self.state == "climb":
            self._climb_step(windows)
        elif self.state == "fall":
            self._fall_step(windows)
        elif self.state == "jump":
            self._jump_step(windows)
        elif self.state in ("idle", "sit", "wave", "crouch"):
            self.timer -= 1
            # Recovery bonus
            self.energy = min(100.0, self.energy + 0.15)
            if self.timer <= 0:
                self._resume_walk()

    def draw(self, cr: cairo.Context) -> None:
        g, s = self.genome, self.genome.scale
        if self.has_shelter and self.home_x is not None:
            draw_shelter(cr, self.home_x or 0.0, self.home_y or 0.0, s)
        if self.fire_timer > 0:
            draw_fire(cr, self.fire_x, self.fire_y, self.t, s)

        color = g.body_color()
        if self.alarm_timer > 0:
            draw_person(
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
                glow=True,
                glow_color=(1, 1, 0, 0.8),
            )

        draw_person(
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

    def _walk_step(self, windows: list[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x += self.vx
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1
        self._check_screen_boundaries(s)
        self._check_window_edges(windows, s)
        floor = self._find_floor(windows)
        if self.y < floor - 3:
            self.state = "fall"
            self.vy = 0.0
            return
        self.y = self.floor_y = floor
        if not self.fleeing:
            self._choose_idle_behavior(self.genome)

    def _check_screen_boundaries(self, s: float) -> None:
        if self.x <= s:
            self.x, self.vx, self.facing = s, abs(self.vx), 1
        elif self.x >= self.sw - s:
            self.x, self.vx, self.facing = self.sw - s, -abs(self.vx), -1

    def _check_window_edges(self, windows: list[WindowSnapshot], s: float) -> bool:
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
        cumulative = 0.0

        # sit_prob
        cumulative += g.sit_prob
        if r < cumulative:
            self._pause("sit", random.randint(100, 380))
            return

        # wave_prob
        cumulative += g.wave_prob
        if r < cumulative:
            self._pause("wave", random.randint(80, 220))
            return

        # run_prob: Trigger a burst of running
        cumulative += g.run_prob
        if r < cumulative:
            self.state = "run"
            self.vx = math.copysign(g.walk_speed * g.run_mult, self.vx)
            return

        # fire_skill: Occasionally start a fire
        cumulative += g.fire_skill
        if r < cumulative and self.fire_timer <= 0:
            self.fire_timer = random.randint(200, 600)
            self.fire_x, self.fire_y = self.x, self.y
            self._pause("crouch", 60)
            return

        # shelter_skill: Build a home
        if not self.has_shelter:
            cumulative += g.shelter_skill
            if r < cumulative:
                self.has_shelter, self.home_x, self.home_y = True, self.x, self.y
                self._pause("crouch", random.randint(200, 450))

    def _climb_step(self, windows: list[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.y -= 2.5
        if self.wall_x is not None:
            self.x = self.wall_x + (-self.wall_side) * s * 0.92
        for win in windows:
            if self.wall_x is not None:
                if (
                    abs(self.wall_x - win.x) < 8
                    or abs(self.wall_x - (win.x + win.w)) < 8
                ) and self.y <= win.y + s:
                    self.y = self.floor_y = float(win.y)
                    self.genome.fitness += 3.0
                    self._resume_walk(side=self.wall_side)
                    return
        if self.y < s * 1.5:
            self.state, self.vy, self.vx = (
                "fall",
                -0.5,
                -self.wall_side * random.uniform(2.0, 4.5),
            )

    def _fall_step(self, windows: list[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx * 0.55))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y = self.floor_y = floor
            self.vy, self.state = 0.0, "walk"
            self.facing = 1 if self.vx > 0 else -1

    def _jump_step(self, windows: list[WindowSnapshot]) -> None:
        s = self.genome.scale
        self.x = max(s, min(self.sw - s, self.x + self.vx))
        self.vy += 0.65
        self.y += self.vy
        floor = self._find_floor(windows)
        if self.y >= floor:
            self.y, self.floor_y, self.vy, self.state = floor, floor, 0.0, "run"

    def _find_floor(self, windows: list[WindowSnapshot]) -> float:
        g = float(self.sh) - self.genome.scale * 0.3
        for win in windows:
            if win.x + 4 < self.x < win.x + win.w - 4 and self.y <= win.y + 3:
                g = min(g, float(win.y))
        return g

    def _begin_climb(self, wall_x: float, side: int) -> None:
        self.state, self.wall_x, self.wall_side, self.facing, self.vx = (
            "climb",
            wall_x,
            side,
            side,
            0.0,
        )

    def _pause(self, state: str, ticks: int) -> None:
        self.state, self.timer, self.vx = state, ticks, 0.0

    def _resume_walk(self, side: int | None = None) -> None:
        self.state, self.wall_x = "walk", None
        spd = self.genome.walk_speed
        self.vx = (
            (side * spd)
            if side is not None
            else (self.vx or random.choice([-1, 1]) * spd)
        )
        self.facing = 1 if self.vx > 0 else -1


class Predator:
    """A predator agent that hunts Persons and evolves over time."""

    SCALE = 22.0

    def __init__(
        self, sw: int, sh: int, config: SimConfig, genome: PredatorGenome | None = None
    ) -> None:
        self.config, self.sw, self.sh = config, sw, sh
        self.genome = genome or PredatorGenome.random()
        self.x, self.y = float(sw // 2), float(sh - self.SCALE * 0.3)
        self.speed = config.pred_base_speed * self.genome.speed_mult
        self.vx, self.vy, self.facing, self.state, self.t, self.kills = (
            self.speed,
            0.0,
            1,
            "run",
            0.0,
            0,
        )
        self.floor_y = self.y
        self.satiation_timer = 0

    def update(self, people: list[Person], windows: list[WindowSnapshot]) -> None:
        self.t += 1
        if people:
            # Only see people within sense_range
            if self.satiation_timer > 0:
                self.satiation_timer -= 1
                # Roam slowly while satiated
                if self.satiation_timer % 50 == 0:
                    self.vx = random.choice([-1, 1]) * (self.speed * 0.3)
            else:
                visible = [
                    p for p in people if abs(p.x - self.x) < self.genome.sense_range
                ]
                if visible:
                    target = min(visible, key=lambda p: abs(p.x - self.x))
                    self.vx = math.copysign(self.speed, target.x - self.x)

        self.x = max(self.SCALE, min(self.sw - self.SCALE, self.x + self.vx))
        self.facing = 1 if self.vx >= 0 else -1
        floor = float(self.sh) - self.SCALE * 0.3
        self.vy += 0.65
        self.y = min(self.y + self.vy, floor)
        if self.y >= floor:
            self.vy = self.y = self.floor_y = floor

    def catch_radius(self) -> float:
        return self.SCALE * 0.85

    def on_kill(self) -> None:
        self.kills += 1
        self.satiation_timer = 200
        self.speed = min(
            self.config.pred_speed_cap, self.speed + self.config.pred_speed_inc
        )

    def draw(self, cr: cairo.Context) -> None:
        draw_person(
            cr,
            self.x,
            self.y,
            self.t,
            self.state,
            self.facing,
            self.SCALE,
            0.5,
            0.42,
            (0.68, 0.08, 0.02, 0.95),
            glow=True,
            glow_color=(1, 0.3, 0.04, 0.62),
        )


class Colony:
    """A collection of evolving Person agents and an optional Predator."""

    def __init__(self, count: int, sw: int, sh: int, *, config: SimConfig) -> None:
        self.config, self.count, self.sw, self.sh, self.tick_n, self.generation = (
            config,
            count,
            sw,
            sh,
            0,
            0,
        )
        self.kill_effects: list[KillEffect] = []
        self.predator = Predator(sw, sh, config) if config.use_predator else None
        self.people = self._load_or_init()

    def _load_or_init(self) -> list[Person]:
        if SAVE_FILE.exists():
            try:
                data = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
                self.generation = int(data.get("generation", 0))
                people = [
                    Person(
                        self.sw,
                        self.sh,
                        Genome.from_dict(d["genome"]),
                        d.get("home_x"),
                        d.get("home_y"),
                    )
                    for d in data.get("people", [])
                ]
                if (
                    "predator_genome" in data
                    and data["predator_genome"]
                    and self.predator
                ):
                    self.predator.genome = PredatorGenome.from_dict(
                        data["predator_genome"]
                    )
                    self.predator.speed = (
                        self.config.pred_base_speed * self.predator.genome.speed_mult
                    )
                while len(people) < self.count:
                    people.append(Person(self.sw, self.sh))
                return people[: self.count]
            except json.JSONDecodeError as e:
                log.error("Failed to parse population JSON: %s", e)
            except Exception as e:
                log.error("Unexpected error loading population: %s", e)
        return [Person(self.sw, self.sh) for _ in range(self.count)]

    def save(self) -> None:
        try:
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
                    "predator_genome": (
                        self.predator.genome.to_dict() if self.predator else None
                    ),
                },
                indent=2,
            )
            SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SAVE_FILE.write_text(payload, encoding="utf-8")
        except OSError as e:
            log.error("Failed to save population to %s: %s", SAVE_FILE, e)
        except Exception as e:
            log.error("Unexpected error saving population: %s", e)

    def tick(self, windows: list[WindowSnapshot]) -> None:
        self.tick_n += 1
        shash = SpatialHash(cell_size=150)
        for p in self.people:
            shash.insert(p, p.x, p.y)

        new_people: list[Person] = []
        dead_count = 0
        for p in self.people:
            p.age += 1
            if p.age > p.max_age:
                dead_count += 1
            else:
                new_people.append(p)

        self.people = new_people

        # Hoist sort outside loop for O(N log N) replacement spawning
        if dead_count > 0:
            if len(self.people) >= 2:
                ranked = sorted(
                    self.people,
                    key=lambda person: person.genome.fitness,
                    reverse=True,
                )
                parents = ranked[: max(2, len(ranked) // 2)]
            else:
                parents = []

            for _ in range(dead_count):
                if len(self.people) >= 2 and parents:
                    a = random.choice(parents)
                    b = self._select_mate(parents, a)
                    child = Person(
                        self.sw,
                        self.sh,
                        Genome.crossover(a.genome, b.genome),
                    )
                    self.people.append(child)
                else:
                    self.people.append(Person(self.sw, self.sh))

        for p in self.people:
            p.update(windows)
        self._handle_interactions(shash)
        if self.predator:
            self._handle_predator(windows, shash)
        for ke in self.kill_effects:
            ke.age += 1
        self.kill_effects = [ke for ke in self.kill_effects if ke.age < ke.max_age]
        if self.config.evolve_every > 0 and self.tick_n % self.config.evolve_every == 0:
            self._evolve()
            self.save()

    def _handle_interactions(self, shash: SpatialHash) -> None:
        active_fires = [(p.fire_x, p.fire_y) for p in self.people if p.fire_timer > 0]
        for a in self.people:
            # Fire energy boost
            if active_fires:
                for fx, fy in active_fires:
                    if math.hypot(a.x - fx, a.y - fy) < 100:
                        a.energy = min(100.0, a.energy + 0.5)
                        break
            if a.energy < 60:
                continue
            # Use social_r trait for interaction radius
            interaction_radius = a.genome.social_r * 35.0
            neighbors = shash.query(a.x, a.y, interaction_radius)
            for b in neighbors:
                if a is b or b.energy >= 40:
                    continue
                # Use Euclidean distance check since SpatialHash returns bounding box
                if math.hypot(b.x - a.x, b.y - a.y) > interaction_radius:
                    continue
                r = a.genome.relatedness(b.genome)
                # Kin selection based sharing
                if r * 20.0 > 8.0:
                    # Invariant violation fix: clamp energy transfer to avoid negative energy
                    amt = min(10 * a.genome.altruism, a.energy)
                    a.energy -= amt
                    b.energy += amt
                    a.genome.fitness += 0.8 * r

    def _handle_predator(
        self, windows: list[WindowSnapshot], shash: SpatialHash
    ) -> None:
        pred = self.predator
        if not pred:
            return
        pred.update(self.people, windows)

        # Clear fleeing flag first to prevent overwriting altruistic signals
        for p in self.people:
            p.fleeing = False

        for p in self.people:
            if abs(p.x - pred.x) < self.config.flee_radius_x:
                p.fleeing = True
                if random.random() < p.genome.altruism and p.alarm_timer <= 0:
                    p.alarm_timer = 60
                    neighbors = shash.query(p.x, p.y, 400)
                    for kin in neighbors:
                        if kin is p:
                            continue
                        # Use Euclidean distance check since SpatialHash returns bounding box
                        if math.hypot(kin.x - p.x, kin.y - p.y) <= 400:
                            r = p.genome.relatedness(kin.genome)
                            if r * 50.0 > 5.0:
                                kin.fleeing = True

        for p in self.people:
            if p.fleeing and p.state not in ("climb", "fall", "jump"):
                p.state, p.vx = (
                    "run",
                    (-1 if pred.x > p.x else 1)
                    * p.genome.walk_speed
                    * p.genome.run_mult,
                )

        catch_r = pred.catch_radius()

        # Batch deletion: O(N) filtering rather than O(N^2) list.remove
        survivors = []
        kill_count = 0
        for p in self.people:
            if math.hypot(p.x - pred.x, p.y - pred.y) < catch_r:
                self.kill_effects.append(KillEffect(p.x, p.y))
                pred.on_kill()
                kill_count += 1
            else:
                survivors.append(p)

        self.people = survivors

        # Spawn replacements
        for _ in range(kill_count):
            self._spawn_replacement(pred)

        if pred.kills >= 5:
            self._predator_reproduction()

    def _predator_reproduction(self) -> None:
        if not self.predator:
            return
        log.info("Predator evolved!")
        self.predator.genome = self.predator.genome.mutate()
        self.predator.kills = 0
        self.predator.speed = (
            self.config.pred_base_speed * self.predator.genome.speed_mult
        )

    def _mate_score(self, a: Person, b: Person) -> float:
        """Calculate mating score based on spatial proximity and sexual selection."""
        # Island Speciation: Closer individuals are much more likely to mate
        dist = math.hypot(a.x - b.x, a.y - b.y)
        spatial_score = 1.0 / (1.0 + dist * 0.05)

        # Sexual Selection: Preference for display trait (hue_r)
        trait_diff = abs(a.genome.mating_preference - b.genome.hue_r)
        sexual_score = 1.0 / (1.0 + trait_diff * 10.0)

        return spatial_score * sexual_score

    def _select_mate(self, pool: list[Person], parent: Person) -> Person:
        """Select a mate for a parent using sexual selection and island speciation rules."""
        if len(pool) < 2:
            return pool[0] if pool else parent

        candidates = [p for p in pool if p is not parent]
        if not candidates:
            return parent

        # Roulette wheel selection based on mate score
        scores = [self._mate_score(parent, c) for c in candidates]
        total_score = sum(scores)

        if total_score <= 0:
            return random.choice(candidates)

        pick = random.uniform(0, total_score)
        current = 0.0
        for c, score in zip(candidates, scores):
            current += score
            if current >= pick:
                return c
        return candidates[-1]

    def _spawn_replacement(self, pred: Predator) -> None:
        if len(self.people) < 2:
            self.people.append(Person(self.sw, self.sh))
            return
        far = sorted(self.people, key=lambda p: abs(p.x - pred.x), reverse=True)
        parents = far[: max(2, len(far) // 2)]
        a = random.choice(parents)
        b = self._select_mate(parents, a)
        child = Person(
            self.sw, self.sh, Genome.crossover(a.genome, b.genome), a.home_x, a.home_y
        )
        self.people.append(child)

    def _evolve(self) -> None:
        self.generation += 1
        if not self.people:
            return
        ranked = sorted(self.people, key=lambda p: p.genome.fitness, reverse=True)
        parents = ranked[: max(2, len(self.people) // 2)]
        for loser in ranked[len(parents) :]:
            a = random.choice(parents)
            b = self._select_mate(parents, a)
            loser.genome = Genome.crossover(a.genome, b.genome)
            loser.energy = 100.0
            loser.state = "walk"
        for p in self.people:
            p.genome.fitness = 0

    def react_to_windows(
        self, old_wins: list[WindowSnapshot], new_wins: list[WindowSnapshot]
    ) -> None:
        gone = {w.id for w in old_wins} - {w.id for w in new_wins}
        for p in self.people:
            for win in old_wins:
                if (
                    win.id in gone
                    and abs(p.floor_y - win.y) < 10
                    and win.x < p.x < win.x + win.w
                ):
                    p.state, p.vy = "jump", -random.uniform(5, 9)

    def stats(self) -> str:
        if not self.people:
            return "extinct"
        avg_e = sum(p.energy for p in self.people) / len(self.people)
        pred_info = f" | pred-spd {self.predator.speed:.1f}" if self.predator else ""
        return f"gen {self.generation} | energy {avg_e:.1f}{pred_info}"
