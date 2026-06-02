import pytest
from unittest.mock import patch
from shadowmen.ui.panel import install_autostart, _autostart_args
from shadowmen.config import SimConfig

def test_autostart_args_defaults():
    cfg = SimConfig()
    args = _autostart_args(cfg)
    assert args == ""

def test_autostart_args_custom():
    cfg = SimConfig(population=50, use_predator=True, evo_speed=2.0)
    args = _autostart_args(cfg)
    assert "--count 50" in args
    assert "--predator" in args
    assert "--evo-speed 2.00" in args

def test_install_autostart(tmp_path):
    autostart_file = tmp_path / "shadowmen.desktop"
    cfg = SimConfig(population=10)
    
    with patch("shadowmen.ui.panel.AUTOSTART_FILE", autostart_file):
        success = install_autostart(cfg)
        assert success is True
        assert autostart_file.exists()
        content = autostart_file.read_text()
        assert "Exec=shadowmen --count 10" in content

def test_install_autostart_failure():
    with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
        success = install_autostart(SimConfig())
        assert success is False
