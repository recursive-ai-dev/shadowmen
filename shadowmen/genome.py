from __future__ import annotations

import random
from dataclasses import dataclass, field, fields
from typing import ClassVar

TRAITS: dict[str, tuple[float, float, float]] = {
    #  name           lo       hi      default
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
}


@dataclass
class Genome:
    """Heritable trait set for one shadow person."""

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
    fitness: float = field(default=0.0, compare=False)

    # --- Backwards-compatible improvements ---

    # Allow injection for reproducible testing
    _rng: ClassVar[random.Random] = random

    @classmethod
    def _get_rng(cls) -> random.Random:
        return cls._rng

    @classmethod
    def set_rng(cls, rng: random.Random) -> None:
        """Replace the internal RNG (useful for deterministic testing)."""
        cls._rng = rng

    @classmethod
    def random(cls) -> Genome:
        """Return a genome with all traits drawn uniformly from their allowed ranges."""
        rng = cls._get_rng()
        kwargs = {k: rng.uniform(v[0], v[1]) for k, v in TRAITS.items()}
        kwargs["fitness"] = 0.0
        return cls(**kwargs)

    @classmethod
    def crossover(
        cls,
        a: Genome,
        b: Genome,
        mutation_rate: float = 0.18,
        mutation_std_factor: float = 0.10,
    ) -> Genome:
        """Produce an offspring genome via uniform crossover with Gaussian mutation.

        Args:
            mutation_std_factor: multiplier for (hi - lo) to compute std dev.
                Defaults to 0.10 for backwards compatibility.
        """
        rng = cls._get_rng()
        kwargs = {}
        for trait, (lo, hi, _) in TRAITS.items():
            val = getattr(a, trait) if rng.random() < 0.5 else getattr(b, trait)
            if rng.random() < mutation_rate:
                std_dev = (hi - lo) * mutation_std_factor
                val += rng.gauss(0, std_dev)
                val = max(lo, min(hi, val))
            kwargs[trait] = val
        kwargs["fitness"] = 0.0
        return cls(**kwargs)

    def body_color(self) -> tuple[float, float, float, float]:
        """Return an RGBA body colour derived from the hue-shift genes."""
        return (
            max(0.0, min(0.28, 0.04 + self.hue_r)),
            0.04,
            max(0.0, min(0.40, 0.12 + self.hue_b)),
            0.95,
        )

    def to_dict(self, include_fitness: bool = False) -> dict[str, float]:
        """Serialise evolvable traits to a plain dict.

        Args:
            include_fitness: if True, include the fitness field.
            Defaults to False for backwards compatibility.
        """
        d = {k: getattr(self, k) for k in TRAITS}
        if include_fitness:
            d["fitness"] = self.fitness
        return d

    @classmethod
    def from_dict(
        cls,
        d: dict[str, float],
        strict: bool = False,
        allow_extra: bool = True,
    ) -> Genome:
        """Deserialise a genome from a plain dict.

        Args:
            strict: if True, reject missing keys (raises KeyError).
                Defaults to False for backwards compatibility.
            allow_extra: if True, silently ignore extra keys.
                Defaults to True for backwards compatibility.
        """
        kwargs = {}
        for k, (lo, hi, default) in TRAITS.items():
            if k in d:
                try:
                    val = float(d[k])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Trait '{k}' must be numeric, got {type(d[k]).__name__}: {d[k]!r}"
                    ) from exc
                # Clamp to valid range as a safety net
                val = max(lo, min(hi, val))
                kwargs[k] = val
            else:
                if strict:
                    raise KeyError(f"Missing required trait '{k}' in dict")
                kwargs[k] = default

        if not allow_extra:
            allowed = set(TRAITS) | {"fitness"}
            extras = set(d) - allowed
            if extras:
                raise ValueError(f"Unexpected keys in dict: {extras}")

        kwargs["fitness"] = 0.0
        return cls(**kwargs)

    def __repr__(self) -> str:
        """Concise representation for debugging."""
        parts = [f"{k}={getattr(self, k):.3f}" for k in TRAITS]
        return f"Genome({', '.join(parts)}, fitness={self.fitness:.3f})"
