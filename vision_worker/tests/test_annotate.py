from __future__ import annotations

import numpy as np
from vision_worker.pipeline.annotate import annotate_frame, encode_jpeg
from vision_worker.types import BoundingBox, Track


def _track(track_id: int, x1: float, y1: float, x2: float, y2: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="person",
        box=BoundingBox(x1, y1, x2, y2),
        confidence=0.87,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def test_annotate_does_not_mutate_input_frame():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    original = frame.copy()
    annotate_frame(frame, [_track(1, 10, 10, 50, 50)])
    assert np.array_equal(frame, original)


def test_annotate_empty_track_list_returns_unchanged_frame():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = annotate_frame(frame, [])
    assert np.array_equal(result, frame)


def test_annotate_handles_out_of_bounds_box_without_crashing():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Box extends far outside the frame -- must be clamped, not crash.
    result = annotate_frame(frame, [_track(1, -50, -50, 500, 500)])
    assert result.shape == frame.shape


def test_annotate_handles_degenerate_box_without_crashing():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = annotate_frame(frame, [_track(1, 50, 50, 50, 50)])
    assert result.shape == frame.shape


def test_encode_jpeg_produces_valid_jpeg_bytes():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    data = encode_jpeg(frame)
    assert data[:2] == b"\xff\xd8"  # JPEG magic bytes
    assert len(data) > 0
