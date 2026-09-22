from __future__ import annotations

from vision_worker.rules.geometry import (
    denormalize_polygon,
    euclidean_distance,
    point_in_polygon,
)

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_point_clearly_inside_square():
    assert point_in_polygon((5, 5), SQUARE) is True


def test_point_clearly_outside_square():
    assert point_in_polygon((50, 50), SQUARE) is False


def test_point_outside_to_the_left():
    assert point_in_polygon((-5, 5), SQUARE) is False


def test_polygon_with_fewer_than_three_points_is_never_inside():
    assert point_in_polygon((0, 0), [(0, 0), (1, 1)]) is False
    assert point_in_polygon((0, 0), []) is False


def test_concave_polygon_l_shape():
    # An L-shaped polygon: the notch at (5,5)-(10,5)-(10,10)-(5,10) is
    # carved out of a 10x10 square.
    l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
    assert point_in_polygon((2, 2), l_shape) is True  # in the solid part
    assert point_in_polygon((7, 7), l_shape) is False  # in the notch


def test_denormalize_polygon_scales_to_frame_size():
    normalized = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)]
    pixels = denormalize_polygon(normalized, frame_width=1000, frame_height=800)
    assert pixels == [(0.0, 0.0), (500.0, 0.0), (500.0, 400.0), (0.0, 400.0)]


def test_euclidean_distance():
    assert euclidean_distance((0, 0), (3, 4)) == 5.0
    assert euclidean_distance((1, 1), (1, 1)) == 0.0
