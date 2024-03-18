from laserscape import *
from unittest.mock import MagicMock
import pytest


@pytest.mark.parametrize(("label_name", "result"),
    [
        ("Engrave", True),
        ("engrave", True),
        ("enGrAve-foo", True),
        ("-foo", False),
        ("cut", False),
        ("ENGRAVE-2", True),
    ]
)
def test_Layer_is_engrave_layer(label_name, result):
    inkscape_layer = MagicMock()
    inkscape_layer.label = label_name
    assert Layer(inkscape_layer).is_engrave_layer()== result


@pytest.mark.parametrize(("label_name", "result"),
    [
        ("Engrave", False),
        ("engrave", False),
        ("enGrAve-foo", False),
        ("-foo", False),
        ("cut", True),
        ("ENGRAVE-2", False),
        ("CUT", True),
        ("CuT-42", True),
    ]
)
def test_Layer_is_cut_layer(label_name, result):
    inkscape_layer = MagicMock()
    inkscape_layer.label = label_name
    assert Layer(inkscape_layer).is_cut_layer()== result


@pytest.mark.parametrize(("label_name", "result"),
    [
        ("Engrave-42", 42),
        ("cut-2", 2),
        ("cut", float("inf")),
    ]
)
def test_priority(label_name, result):
    inkscape_layer = MagicMock()
    inkscape_layer.label = label_name
    assert Layer(inkscape_layer).priority == result


@pytest.mark.parametrize(("label_name", "result"),
    [
        ("Engrave-42", 1),
        ("cut-2", 1),
        ("cut", 1),
        ("cutx42", 42),
        ("cut-5x2", 2),
        ("engravex4", 4),
        ("engrave-45x3", 3),
        ("cutx1", 1)
    ]
)
def test_passes(label_name, result):
    inkscape_layer = MagicMock()
    inkscape_layer.label = label_name
    assert Layer(inkscape_layer).passes == result
