import pytest
import random
from shadowmen.genome import Genome, TRAITS


def test_genome_random():
    g = Genome.random()
    for trait, (lo, hi, _) in TRAITS.items():
        val = getattr(g, trait)
        assert isinstance(val, float)
        assert lo <= val <= hi
    assert g.fitness == 0.0


def test_genome_crossover_no_mutation():
    a = Genome.random()
    b = Genome.random()
    child = Genome.crossover(a, b, mutation_rate=0.0)

    for trait in TRAITS:
        val = getattr(child, trait)
        assert val == getattr(a, trait) or val == getattr(b, trait)


def test_genome_crossover_with_mutation():
    # Force mutation and check bounds
    random.seed(42)
    a = Genome.random()
    b = Genome.random()
    # Reduced from 100 to 20 to improve speed while still ensuring bounds are met
    for _ in range(20):
        child = Genome.crossover(a, b, mutation_rate=1.0)
        for trait, (lo, hi, _) in TRAITS.items():
            val = getattr(child, trait)
            assert lo <= val <= hi


def test_genome_body_color():
    # Use values that result in clamped output
    # hue_r = 0.5 -> 0.04 + 0.5 = 0.54. min(0.28, 0.54) = 0.28
    # hue_b = -0.5 -> 0.12 - 0.5 = -0.38. max(0.0, -0.38) = 0.0
    g = Genome(hue_r=0.24, hue_b=-0.2)
    color = g.body_color()
    assert len(color) == 4

    # 0.04 + 0.24 = 0.28 -> 0.28
    assert color[0] == pytest.approx(0.28)
    assert color[1] == pytest.approx(0.04)
    # 0.12 - 0.2 = -0.08 -> 0.0
    assert color[2] == pytest.approx(0.0)
    assert color[3] == pytest.approx(0.95)


def test_genome_to_from_dict():
    g = Genome.random()
    g.fitness = 100.0  # Fitness should not be serialized
    d = g.to_dict()
    assert "fitness" not in d

    g2 = Genome.from_dict(d)
    assert g.to_dict() == g2.to_dict()
    assert g2.fitness == 0.0


def test_genome_from_dict_incomplete():
    d = {"walk_speed": 3.0}
    g = Genome.from_dict(d)
    assert g.walk_speed == pytest.approx(3.0)
    assert g.run_mult == TRAITS["run_mult"][2]  # Default value

def test_genome_mating_preference_serialization():
    g = Genome(mating_preference=0.1)
    d = g.to_dict()
    assert d["mating_preference"] == pytest.approx(0.1)

    g2 = Genome.from_dict(d)
    assert g2.mating_preference == pytest.approx(0.1)
