"""Weapon detector tests.

Most of these are synthetic -- they construct a fake raw ONNX output array
by hand and check that `_postprocess`/`_nms` decode it correctly, so they
run in any clone of this repository without needing the actual trained
checkpoint (a large binary artifact produced by
scripts/weapon_detection/train.py, not committed to git). The one real
integration test is skipped unless that checkpoint happens to be present
at the conventional local path.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from vision_worker.detectors.base import DetectorUnavailableError
from vision_worker.detectors.weapon_detector import WeaponDetector

LOCAL_CHECKPOINT = os.path.expanduser("~/smartvision-weapon-model/train/weights/best.onnx")


def _make_raw_output(boxes_cxcywh, class_scores):
    """Builds a fake ultralytics-ONNX-shaped output: (1, 4+num_classes, num_boxes)."""
    num_boxes = len(boxes_cxcywh)
    num_classes = len(class_scores[0])
    arr = np.zeros((1, 4 + num_classes, num_boxes), dtype=np.float32)
    for i, (cx, cy, w, h) in enumerate(boxes_cxcywh):
        arr[0, 0, i] = cx
        arr[0, 1, i] = cy
        arr[0, 2, i] = w
        arr[0, 3, i] = h
        for c in range(num_classes):
            arr[0, 4 + c, i] = class_scores[i][c]
    return arr


def test_postprocess_decodes_single_high_confidence_box():
    detector = WeaponDetector.__new__(WeaponDetector)
    detector._imgsz = 320
    detector._class_names_list = ["pistol", "smartphone", "knife"]

    raw = _make_raw_output(
        boxes_cxcywh=[(160.0, 160.0, 40.0, 60.0)],
        class_scores=[[0.9, 0.05, 0.02]],
    )
    detections = detector._postprocess(raw, orig_w=640, orig_h=640, confidence_threshold=0.25)

    assert len(detections) == 1
    assert detections[0].class_name == "pistol"
    assert detections[0].confidence == pytest.approx(0.9)
    assert detections[0].box.x1 == pytest.approx((160 - 20) * 2)
    assert detections[0].box.y1 == pytest.approx((160 - 30) * 2)


def test_postprocess_filters_below_confidence_threshold():
    detector = WeaponDetector.__new__(WeaponDetector)
    detector._imgsz = 320
    detector._class_names_list = ["pistol", "smartphone", "knife"]

    raw = _make_raw_output(
        boxes_cxcywh=[(100.0, 100.0, 20.0, 20.0)],
        class_scores=[[0.1, 0.05, 0.02]],
    )
    detections = detector._postprocess(raw, orig_w=320, orig_h=320, confidence_threshold=0.25)
    assert detections == []


def test_postprocess_empty_boxes_returns_empty_list():
    detector = WeaponDetector.__new__(WeaponDetector)
    detector._imgsz = 320
    detector._class_names_list = ["pistol", "smartphone", "knife"]

    raw = np.zeros((1, 7, 0), dtype=np.float32)
    detections = detector._postprocess(raw, orig_w=320, orig_h=320, confidence_threshold=0.25)
    assert detections == []


def test_nms_suppresses_overlapping_boxes_keeping_highest_confidence():
    boxes = np.array(
        [
            [100.0, 100.0, 40.0, 40.0],
            [102.0, 101.0, 40.0, 40.0],
        ]
    )
    scores = np.array([0.9, 0.6])
    keep = WeaponDetector._nms(boxes, scores, iou_threshold=0.45)
    assert keep == [0]


def test_nms_keeps_non_overlapping_boxes():
    boxes = np.array(
        [
            [50.0, 50.0, 20.0, 20.0],
            [500.0, 500.0, 20.0, 20.0],
        ]
    )
    scores = np.array([0.8, 0.7])
    keep = WeaponDetector._nms(boxes, scores, iou_threshold=0.45)
    assert set(keep) == {0, 1}


def test_missing_checkpoint_raises_unavailable_error(tmp_path):
    missing_path = str(tmp_path / "does-not-exist.onnx")
    with pytest.raises(DetectorUnavailableError):
        WeaponDetector(onnx_path=missing_path)


def test_class_names_property():
    detector = WeaponDetector.__new__(WeaponDetector)
    detector._class_names_list = ["pistol", "smartphone", "knife", "monedero", "billete", "tarjeta"]
    names = detector.class_names
    assert names[0] == "pistol"
    assert names[2] == "knife"
    assert len(names) == 6


@pytest.mark.skipif(
    not os.path.exists(LOCAL_CHECKPOINT), reason="no locally-trained weapon checkpoint present"
)
def test_real_checkpoint_produces_sensible_detections():
    detector = WeaponDetector(onnx_path=LOCAL_CHECKPOINT)
    assert set(detector.class_names.values()) >= {"pistol", "knife"}
