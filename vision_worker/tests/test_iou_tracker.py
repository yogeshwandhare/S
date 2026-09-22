"""Tracker unit tests. All detections here are synthetic test fixtures --
no model inference or real video involved, per the project brief's
requirement that rule/tracker tests use synthetic tracks."""

from __future__ import annotations

from vision_worker.trackers.iou_tracker import IoUTracker
from vision_worker.types import BoundingBox, Detection


def _det(
    x1: float, y1: float, x2: float, y2: float, cls: str = "person", conf: float = 0.9
) -> Detection:
    return Detection(box=BoundingBox(x1, y1, x2, y2), class_id=0, class_name=cls, confidence=conf)


def test_new_detection_creates_new_track():
    tracker = IoUTracker()
    tracks = tracker.update([_det(0, 0, 50, 100)])
    assert len(tracks) == 1
    assert tracks[0].track_id == 1


def test_same_object_next_frame_keeps_same_track_id():
    tracker = IoUTracker()
    tracker.update([_det(0, 0, 50, 100)])
    # Small movement between frames -- still high IoU.
    tracks = tracker.update([_det(2, 2, 52, 102)])
    assert len(tracks) == 1
    assert tracks[0].track_id == 1


def test_far_away_detection_gets_new_track_id():
    tracker = IoUTracker()
    tracker.update([_det(0, 0, 50, 100)])
    tracks = tracker.update([_det(500, 500, 550, 600)])
    # Original track ages out (missed), new detection becomes track 2.
    assert any(t.track_id == 2 for t in tracks)


def test_track_survives_brief_occlusion_within_grace_period():
    tracker = IoUTracker(max_missed_frames=3)
    tracker.update([_det(0, 0, 50, 100)])
    # Object disappears for 2 frames (within the 3-frame grace period).
    tracker.update([])
    tracker.update([])
    # Reappears in roughly the same place.
    tracks = tracker.update([_det(3, 3, 53, 103)])
    assert len(tracks) == 1
    assert tracks[0].track_id == 1


def test_track_dropped_after_exceeding_missed_frames():
    tracker = IoUTracker(max_missed_frames=2)
    tracker.update([_det(0, 0, 50, 100)])
    tracker.update([])
    tracker.update([])
    tracker.update([])  # 3 missed frames > max of 2
    tracks = tracker.update([_det(3, 3, 53, 103)])
    # The old track should have been dropped; this is a *new* track.
    assert tracks[0].track_id == 2


def test_different_classes_never_matched_to_same_track():
    tracker = IoUTracker()
    tracker.update([_det(0, 0, 50, 100, cls="person")])
    # Same box, different class -- must not reuse the person's track id.
    tracks = tracker.update([_det(0, 0, 50, 100, cls="backpack")])
    # Both tracks coexist: the person track ages (not yet dropped) and a
    # brand-new track is created for the backpack detection.
    assert len(tracks) == 2
    backpack_tracks = [t for t in tracks if t.class_name == "backpack"]
    person_tracks = [t for t in tracks if t.class_name == "person"]
    assert len(backpack_tracks) == 1
    assert len(person_tracks) == 1
    assert backpack_tracks[0].track_id != person_tracks[0].track_id
    assert person_tracks[0].missed_frames == 1


def test_multiple_simultaneous_objects_get_distinct_ids():
    tracker = IoUTracker()
    tracks = tracker.update([_det(0, 0, 50, 100), _det(200, 200, 260, 320)])
    assert len(tracks) == 2
    assert {t.track_id for t in tracks} == {1, 2}


def test_footpoint_history_accumulates_and_is_bounded():
    tracker = IoUTracker()
    box = _det(0, 0, 50, 100)
    for _ in range(200):
        tracks = tracker.update([box])
    # History length is capped -- must not grow unbounded over a long-running
    # camera session.
    assert len(tracks[0].footpoint_history) <= 90


def test_reset_clears_all_tracks_and_restarts_ids():
    tracker = IoUTracker()
    tracker.update([_det(0, 0, 50, 100)])
    tracker.reset()
    tracks = tracker.update([_det(0, 0, 50, 100)])
    assert tracks[0].track_id == 1
    assert len(tracker.active_tracks) == 1
