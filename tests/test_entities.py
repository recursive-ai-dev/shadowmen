import pytest
import math
import json
from unittest.mock import MagicMock, patch
from shadowmen.entities import Person, Predator, Colony, KillEffect
from shadowmen.genome import Genome
from shadowmen.config import SimConfig
from shadowmen.utils import WindowSnapshot, SpatialHash


@pytest.fixture
def config():
    return SimConfig()


def test_person_init_random():
    p = Person(1920, 1080)
    assert isinstance(p.genome, Genome)
    assert p.x >= p.genome.scale
    assert p.x <= 1920 - p.genome.scale
    assert p.has_shelter is False


def test_person_init_home():
    p = Person(1920, 1080, home_x=500, home_y=500)
    assert p.x == 500
    assert p.y == 500
    assert p.home_x == 500
    assert p.home_y == 500
    assert p.has_shelter is True


def test_person_update_walk(config):
    # Fix seed to ensure predictable velocity
    with patch("random.choice", return_value=1.0):
        p = Person(1920, 1080)
        p.state = "walk"
        p.vx = 2.2
        initial_x = p.x
        p.update([])
        assert p.x == pytest.approx(initial_x + p.vx)
        assert p.genome.fitness > 0


def test_person_climb_logic():
    p = Person(1920, 1080)
    p._begin_climb(100.0, 1)
    assert p.state == "climb"
    assert p.wall_x == 100.0
    assert p.wall_side == 1

    initial_y = p.y
    p.update([])
    assert p.y == initial_y - 2.5
    assert p.x == 100.0 + (-1) * p.genome.scale * 0.92


def test_person_fall_to_floor():
    p = Person(1920, 1080)
    p.y = 500
    p.state = "fall"
    p.vy = 0
    p.update([])  # Apply gravity
    assert p.vy == 0.65
    assert p.y == 500.65

    # Fast forward to floor
    p.y = 1080 - p.genome.scale * 0.3 - 0.1
    p.update([])
    assert p.state == "walk"
    assert p.y == 1080 - p.genome.scale * 0.3


def test_person_boundary_collision():
    p = Person(1920, 1080)
    p.x = 10
    p.vx = -2.0
    p.genome.scale = 20
    # Mock random to return 1.0, preventing climb_prob trigger
    with patch("random.random", return_value=1.0):
        # Should bounce
        p._check_screen_boundaries(p.genome.scale)
        assert p.x == 20
        assert p.vx == 2.0
        assert p.facing == 1


def test_predator_hunt(config):
    pred = Predator(1920, 1080, config)
    p = Person(1920, 1080)
    p.x = pred.x + 100
    p.y = pred.y

    pred.update([p], [])
    assert pred.vx > 0  # Moving towards person

    pred.x = p.x + 100
    pred.update([p], [])
    assert pred.vx < 0  # Moving towards person


def test_predator_on_kill(config):
    pred = Predator(1920, 1080, config)
    initial_speed = pred.speed
    pred.on_kill()
    assert pred.kills == 1
    assert pred.speed == initial_speed + config.pred_speed_inc


def test_colony_save_load(config, tmp_path):
    save_file = tmp_path / "save.json"
    with patch("shadowmen.entities.SAVE_FILE", save_file):
        colony = Colony(5, 1920, 1080, config=config)
        colony.save()
        assert save_file.exists()

        colony2 = Colony(5, 1920, 1080, config=config)
        assert len(colony2.people) == 5
        assert colony2.generation == 0


def test_colony_evolve(config, tmp_path):
    # Isolate save file
    save_file = tmp_path / "save_evolve.json"
    with patch("shadowmen.entities.SAVE_FILE", save_file):
        colony = Colony(10, 1920, 1080, config=config)
        colony.generation = 0
        for p in colony.people:
            p.genome.fitness = 10.0
        colony.people[0].genome.fitness = 100.0  # Clear winner

        colony._evolve()
        assert colony.generation == 1
        # Check that fitness was reset
        for p in colony.people:
            assert p.genome.fitness == 0.0


def test_colony_interactions(config):
    colony = Colony(2, 1920, 1080, config=config)
    a, b = colony.people
    a.x = 100
    b.x = 105
    a.y = b.y = 1080 - a.genome.scale * 0.3
    a.state = b.state = "walk"
    a.energy = 100
    b.energy = 20

    # Ensure they are kin
    a.genome = Genome()
    b.genome = Genome()
    a.genome.altruism = 1.0

    shash = SpatialHash()
    shash.insert(a, a.x, a.y)
    shash.insert(b, b.x, b.y)

    colony._handle_interactions(shash)
    assert a.energy < 100
    assert b.energy > 20


def test_colony_react_to_windows(config):
    colony = Colony(1, 1920, 1080, config=config)
    p = colony.people[0]
    p.x = 100
    p.y = p.floor_y = 500
    p.state = "idle"

    old_wins = [WindowSnapshot(90, 500, 100, 20, "win1")]
    new_wins = []  # Window closed

    colony.react_to_windows(old_wins, new_wins)
    assert p.state == "jump"
    assert p.vy < 0
