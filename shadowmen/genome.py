from __future__ import annotations
import random
import math
from dataclasses import dataclass, field
from typing import ClassVar, Dict, Tuple

TRAITS: Dict[str, Tuple[float, float, float]] = {
    "walk_speed": (1.2, 4.8, 2.2),
    "run_mult": (1.8, 3.5, 2.4),
    "scale": (13.0, 28.0, 18.0),
    "climb_prob": (0.002, 0.09, 0.018),
    "sit_prob": (0.0004, 0.007, 0.0013),
    "run_prob": (0.0004, 0.007, 0.0024),
    "wave_prob": (0.0004, 0.007, 0.0013),
    "social_r": (0.6, 4.2, 1.8),
    "leg_amp": (0.20, 0.58, 0.36),
    "arm_amp": (0.14, 0.48, 0.28),
    "hue_r": (-0.04, 0.15, 0.0),
    "hue_b": (-0.04, 0.24, 0.0),
    "fire_skill": (0.0001, 0.005, 0.001),
    "shelter_skill": (0.0001, 0.005, 0.0008),
    "altruism": (0.0, 1.0, 0.1),
    "metabolism": (0.01, 0.1, 0.05),
}

@dataclass
class Genome:
    walk_speed: float = 2.2
    run_mult: float = 2.4
    scale: float = 18.0
    climb_prob: float = 0.018
    sit_prob: float = 0.0013
    run_prob: float = 0.0024
    wave_prob: float = 0.0013
    social_r: float = 1.8
    leg_amp: float = 0.36
    arm_amp: float = 0.28
    hue_r: float = 0.0
    hue_b: float = 0.0
    fire_skill: float = 0.001
    shelter_skill: float = 0.0008
    altruism: float = 0.1
    metabolism: float = 0.05
    fitness: float = field(default=0.0, compare=False)

    _rng: ClassVar[random.Random] = random

    @classmethod
    def random(cls) -> Genome:
        rng = cls._rng
        kwargs = {k: rng.uniform(v[0], v[1]) for k, v in TRAITS.items()}
        return cls(**kwargs)

    @classmethod
    def crossover(cls, a: Genome, b: Genome, mutation_rate: float = 0.18) -> Genome:
        rng = cls._rng
        kwargs = {}
        for trait, (lo, hi, _) in TRAITS.items():
            val = getattr(a, trait) if rng.random() < 0.5 else getattr(b, trait)
            if rng.random() < mutation_rate:
                val += rng.gauss(0, (hi - lo) * 0.1)
                val = max(lo, min(hi, val))
            kwargs[trait] = val
        return cls(**kwargs)

    def relatedness(self, other: Genome) -> float:
        """Calculates normalized genetic similarity [0, 1]."""
        dist_sq = 0.0
        for trait, (lo, hi, _) in TRAITS.items():
            r = hi - lo
            if r <= 0: continue
            norm_a = (getattr(self, trait) - lo) / r
            norm_b = (getattr(other, trait) - lo) / r
            dist_sq += (norm_a - norm_b) ** 2
        return 1.0 / (1.0 + math.sqrt(dist_sq))

    def body_color(self) -> Tuple[float, float, float, float]:
        return (max(0.0, min(0.28, 0.04 + self.hue_r)), 0.04, max(0.0, min(0.40, 0.12 + self.hue_b)), 0.95)

    def to_dict(self) -> Dict[str, float]:
        return {k: getattr(self, k) for k in TRAITS}

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> Genome:
        kwargs = {}
        for k, (lo, hi, default) in TRAITS.items():
            val = d.get(k, default)
            kwargs[k] = max(lo, min(hi, float(val)))
        return cls(**kwargs)

@dataclass
class PredatorGenome:
    speed_mult: float = 1.0
    sense_range: float = 600.0
    mutation_rate: float = 0.12

    @classmethod
    def random(cls) -> PredatorGenome:
        return cls(
            speed_mult=random.uniform(0.8, 1.2),
            sense_range=random.uniform(400, 1000)
        )

    def mutate(self) -> PredatorGenome:
        return PredatorGenome(
            speed_mult=max(0.5, min(2.0, self.speed_mult + random.gauss(0, 0.05))),
            sense_range=max(200, min(2000, self.sense_range + random.gauss(0, 50))),
        )

    def to_dict(self) -> Dict[str, float]:
        return {"speed_mult": self.speed_mult, "sense_range": self.sense_range}

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> PredatorGenome:
        return cls(
            speed_mult=float(d.get("speed_mult", 1.0)),
            sense_range=float(d.get("sense_range", 600.0))
        )
