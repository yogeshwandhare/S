from __future__ import annotations

from vision_worker.types import BoundingBox


def test_identical_boxes_have_iou_one():
    a = BoundingBox(0, 0, 100, 100)
    b = BoundingBox(0, 0, 100, 100)
    assert a.iou(b) == 1.0


def test_non_overlapping_boxes_have_iou_zero():
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(100, 100, 110, 110)
    assert a.iou(b) == 0.0


def test_partial_overlap_iou_between_zero_and_one():
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(5, 5, 15, 15)
    iou = a.iou(b)
    assert 0.0 < iou < 1.0
    # Intersection = 5x5=25, union = 100+100-25=175 -> 25/175
    assert abs(iou - (25 / 175)) < 1e-9


def test_footpoint_is_bottom_center():
    box = BoundingBox(0, 0, 100, 200)
    assert box.footpoint == (50.0, 200.0)


def test_center_is_geometric_center():
    box = BoundingBox(0, 0, 100, 200)
    assert box.center == (50.0, 100.0)


def test_degenerate_zero_area_box_does_not_crash_iou():
    a = BoundingBox(10, 10, 10, 10)
    b = BoundingBox(0, 0, 20, 20)
    assert a.iou(b) == 0.0
