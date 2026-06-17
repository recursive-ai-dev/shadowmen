from __future__ import annotations
import random
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
    "altruism": (0.0, 1.0, 0.1),       # New
    "metabolism": (0.01, 0.1, 0.05),   # New
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
        # Optimization: cache items() to avoid repeated lookups
        for trait, (lo, hi, _) in TRAITS.items():
            val = getattr(a, trait) if rng.random() < 0.5 else getattr(b, trait)
            if rng.random() < mutation_rate:
                val += rng.gauss(0, (hi - lo) * 0.1)
                val = max(lo, min(hi, val))
            kwargs[trait] = val
        return cls(**kwargs)

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
