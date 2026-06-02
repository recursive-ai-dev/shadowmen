import pytest
import sys
from unittest.mock import patch, MagicMock
from shadowmen.__main__ import main
from shadowmen.config import SimConfig

def test_main_help(capsys):
    with patch("sys.argv", ["shadowmen", "--help"]):
        with pytest.raises(SystemExit):
            main()
    out, _ = capsys.readouterr()
    assert "Evolving shadow people" in out

def test_main_install_autostart():
    with patch("sys.argv", ["shadowmen", "--install-autostart"]), \
         patch("shadowmen.__main__.install_autostart") as mock_install:
        main()
        mock_install.assert_called_once()

@patch("shadowmen.__main__.ShadowMen")
@patch("shadowmen.__main__.Gtk.main")
@patch("shadowmen.__main__.GLib.timeout_add") # Add this
def test_main_app_start(mock_timeout_add, mock_gtk_main, mock_shadowmen):
    with patch("sys.argv", ["shadowmen", "--count", "12"]):
        main()
        mock_shadowmen.assert_called_once()
        cfg = mock_shadowmen.call_args[0][0]
        assert cfg.population == 12

def test_main_reset():
    with patch("sys.argv", ["shadowmen", "--reset"]), \
         patch("shadowmen.__main__.SAVE_FILE") as mock_save_file:
        mock_save_file.exists.return_value = True
        main()
        mock_save_file.unlink.assert_called_once()
