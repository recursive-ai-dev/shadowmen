import fcntl

import pytest
import shadowmen.config as config_mod
from shadowmen.config import SimConfig, acquire_single_instance_lock


def test_config_defaults():
    cfg = SimConfig()
    assert cfg.population == 8
    assert cfg.use_predator is False


def test_config_validation():
    cfg = SimConfig(population=0)
    errors = cfg.validate()
    assert len(errors) > 0
    assert "population must be ≥ 1" in errors[0]


def test_config_to_from_dict():
    cfg = SimConfig(population=20, use_predator=True)
    d = cfg.to_dict()
    cfg2 = SimConfig.from_dict(d)
    assert cfg.population == cfg2.population
    assert cfg.use_predator == cfg2.use_predator


@pytest.fixture
def _reset_lock():
    # Ensure each test starts without a process-held lock and cleans up after.
    prev = config_mod._lock_handle
    config_mod._lock_handle = None
    yield
    if config_mod._lock_handle is not None:
        config_mod._lock_handle.close()
    config_mod._lock_handle = prev


def test_single_instance_lock_acquires(tmp_path, _reset_lock):
    lock = tmp_path / "shadowmen.lock"
    assert acquire_single_instance_lock(lock) is True
    assert lock.exists()
    # Same process asking again is idempotent, not a second instance.
    assert acquire_single_instance_lock(lock) is True


def test_single_instance_lock_blocks_second(tmp_path, _reset_lock):
    lock = tmp_path / "shadowmen.lock"
    # Simulate a rival instance already holding the flock (independent fd).
    rival = lock.open("a+")
    fcntl.flock(rival.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert acquire_single_instance_lock(lock) is False
    finally:
        rival.close()
