import pytest
from shadowmen.entities import Person, Colony
from shadowmen.config import SimConfig
from shadowmen.genome import Genome
from shadowmen.utils import SpatialHash


def test_person_exhaustion():
    p = Person(1000, 1000)
    p.energy = 0
    p.update([])
    assert p.state == "crouch"
    assert p.vx == 0


def test_person_run_burst():
    # Force a genome with high run_prob and low others
    g = Genome(run_prob=1.0, sit_prob=0, wave_prob=0, fire_skill=0, shelter_skill=0)
    p = Person(1000, 1000, genome=g)
    p.state = "walk"
    p.update([])
    assert p.state == "run"
    assert abs(p.vx) > g.walk_speed


def test_person_fire_trigger():
    g = Genome(fire_skill=1.0, sit_prob=0, wave_prob=0, run_prob=0, shelter_skill=0)
    p = Person(1000, 1000, genome=g)
    p.update([])
    assert p.fire_timer > 0
    assert p.state == "crouch"


def test_colony_interaction_radius():
    cfg = SimConfig(population=2)
    # G1 has small social_r, G2 has large social_r
    g1 = Genome(social_r=0.1, altruism=1.0)
    g2 = Genome(social_r=5.0, altruism=1.0)

    colony = Colony(2, 1000, 1000, config=cfg)
    p1 = Person(1000, 1000, genome=g1)
    p2 = Person(1000, 1000, genome=g2)
    p1.x, p1.y = 500, 500
    p2.x, p2.y = 600, 500  # 100px apart

    colony.people = [p1, p2]

    # Radius for p1: 0.1 * 35 = 3.5 (too small)
    # Radius for p2: 5.0 * 35 = 175 (should reach p1)

    p1.energy = 100
    p2.energy = 30
    p1.genome = p2.genome  # Ensure relatedness

    shash = SpatialHash()
    shash.insert(p1, p1.x, p1.y)
    shash.insert(p2, p2.x, p2.y)

    colony._handle_interactions(shash)

    assert p2.energy > 30
    assert p1.energy < 100


def test_sexual_selection():
    """Verify that individuals prefer mates with traits matching their preference."""
    colony = Colony(0, 1000, 1000, config=SimConfig())

    # Parent wants a red mate
    parent = Person(1000, 1000, genome=Genome(mating_preference=0.15))
    parent.x, parent.y = 500, 500

    # Potential mates, all equidistant
    m_red = Person(1000, 1000, genome=Genome(hue_r=0.15))
    m_red.x, m_red.y = 500, 500

    m_blue = Person(1000, 1000, genome=Genome(hue_r=-0.04))
    m_blue.x, m_blue.y = 500, 500

    m_neutral = Person(1000, 1000, genome=Genome(hue_r=0.05))
    m_neutral.x, m_neutral.y = 500, 500

    score_red = colony._mate_score(parent, m_red)
    score_blue = colony._mate_score(parent, m_blue)
    score_neutral = colony._mate_score(parent, m_neutral)

    assert score_red > score_neutral
    assert score_neutral > score_blue

    # Calculate probability distribution and mathematically verify
    # score is strictly based on sexual selection since spatial distance is 0
    assert score_red == pytest.approx(1.0)
    assert score_blue == pytest.approx(1.0 / (1.0 + abs(0.15 - (-0.04)) * 10.0))


def test_island_speciation():
    """Verify that spatial distance affects mate selection."""
    colony = Colony(0, 1000, 1000, config=SimConfig())

    parent = Person(1000, 1000, genome=Genome(mating_preference=0.0))
    parent.x, parent.y = 100, 100

    # Identical traits, different distances
    close = Person(1000, 1000, genome=Genome(hue_r=0.0))
    close.x, close.y = 110, 100  # dist = 10

    far = Person(1000, 1000, genome=Genome(hue_r=0.0))
    far.x, far.y = 900, 100  # dist = 800

    score_close = colony._mate_score(parent, close)
    score_far = colony._mate_score(parent, far)

    assert score_close > score_far

    # Mathematically verify spatial score formula
    assert score_close == pytest.approx(1.0 / (1.0 + 10 * 0.05))
    assert score_far == pytest.approx(1.0 / (1.0 + 800 * 0.05))

    # Verify probability of choosing close vs far
    # The _select_mate function should probabilistically prefer close
    pool = [close, far]
    close_chosen = 0
    for _ in range(100):
        if colony._select_mate(pool, parent) == close:
            close_chosen += 1

    # Based on scores, close (~0.666) should be chosen significantly more than far (~0.024)
    assert close_chosen > 75
