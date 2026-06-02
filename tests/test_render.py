import pytest
from unittest.mock import MagicMock, patch
from shadowmen.render import CharacterRenderer, draw_person, draw_fire, draw_shelter

@pytest.fixture
def mock_cr():
    return MagicMock()

def test_person_renderer_dispatch(mock_cr):
    renderer = CharacterRenderer(
        mock_cr, 100, 100, 10, "walk", 1, 20, 0.3, 0.2, (0,0,0,1)
    )
    with patch.object(CharacterRenderer, "_draw_walk_run") as mock_walk:
        renderer.render()
        mock_walk.assert_called_once()

def test_person_renderer_glow(mock_cr):
    renderer = CharacterRenderer(
        mock_cr, 100, 100, 10, "walk", 1, 20, 0.3, 0.2, (0.1, 0.1, 0.1, 1),
        glow=True, glow_color=(1, 1, 1, 1)
    )
    renderer.render()
    mock_cr.set_source_rgba.assert_any_call(1, 1, 1, 1)

def test_draw_fire(mock_cr):
    draw_fire(mock_cr, 100, 100, 10, 20)
    mock_cr.save.assert_called_once()
    mock_cr.restore.assert_called_once()
    mock_cr.translate.assert_called_with(100, 100)
    # Check that it tried to draw something (e.g. arc for glow)
    mock_cr.arc.assert_called()

def test_draw_shelter(mock_cr):
    draw_shelter(mock_cr, 100, 100, 20)
    mock_cr.save.assert_called_once()
    mock_cr.restore.assert_called_once()
    # Check that it drew lines
    mock_cr.line_to.assert_called()
