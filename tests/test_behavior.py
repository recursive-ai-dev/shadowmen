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
    p2.x, p2.y = 600, 500 # 100px apart

    colony.people = [p1, p2]

    # Radius for p1: 0.1 * 35 = 3.5 (too small)
    # Radius for p2: 5.0 * 35 = 175 (should reach p1)

    p1.energy = 100
    p2.energy = 30
    p1.genome = p2.genome # Ensure relatedness

    shash = SpatialHash()
    shash.insert(p1, p1.x, p1.y)
    shash.insert(p2, p2.x, p2.y)

    colony._handle_interactions(shash)

    assert p2.energy > 30
    assert p1.energy < 100
