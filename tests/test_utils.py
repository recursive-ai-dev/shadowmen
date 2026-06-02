import pytest
from unittest.mock import patch, MagicMock
from shadowmen.utils import get_windows

def test_get_windows_no_wmctrl():
    with patch("shutil.which", return_value=None):
        # Reset the global _wmctrl_available for this test
        import shadowmen.utils
        shadowmen.utils._wmctrl_available = None
        
        wins = get_windows(1920, 1080)
        assert wins == []

def test_get_windows_with_mock_output():
    mock_output = (
        "0x01234567  0 100  200  800  600  hostname Window Title\n"
        "0x01234568 -1 0    0    1920 1080 hostname Desktop\n" # Desktop (int(parts[1]) < 0)
        "0x01234569  0 50   50   50   50   hostname Small\n"   # Small (w < 80)
        "0x01234570  0 0    0    1920 1080 hostname FS\n"      # Fullscreen (w >= sw - 10)
    )
    
    with patch("shutil.which", return_value="/usr/bin/wmctrl"), \
         patch("subprocess.check_output", return_value=mock_output):
        import shadowmen.utils
        shadowmen.utils._wmctrl_available = True
        
        wins = get_windows(1920, 1080)
        assert len(wins) == 1
        assert wins[0] == (100, 200, 800, 600)

def test_get_windows_subprocess_error():
    with patch("shutil.which", return_value="/usr/bin/wmctrl"), \
         patch("subprocess.check_output", side_effect=OSError("wmctrl failed")):
        import shadowmen.utils
        shadowmen.utils._wmctrl_available = True
        
        wins = get_windows(1920, 1080)
        assert wins == []

def test_get_windows_malformed_output():
    mock_output = "garbage line\n0x1 0 1 2 3 4" # too few parts
    with patch("shutil.which", return_value="/usr/bin/wmctrl"), \
         patch("subprocess.check_output", return_value=mock_output):
        import shadowmen.utils
        shadowmen.utils._wmctrl_available = True
        
        wins = get_windows(1920, 1080)
        assert wins == []
