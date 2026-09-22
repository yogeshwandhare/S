"""Tests that CameraWorker correctly wires rule evaluation to the
on_rule_triggered callback. Exercises `_evaluate_rules` directly with
synthetic tracks -- no real video or detector needed for this part."""

from __future__ import annotations

from vision_worker.pipeline.source import FrameSource, FrameSourceConfig, SourceType
from vision_worker.pipeline.worker import CameraWorker
from vision_worker.rules.abandoned_object import AbandonedObjectConfig, AbandonedObjectRule
from vision_worker.rules.aggressive_motion import AggressiveMotionConfig, AggressiveMotionRule
from vision_worker.rules.intrusion import ZoneConfig, ZoneIntrusionRule
from vision_worker.rules.weapon_confirmation import WeaponConfirmationConfig, WeaponConfirmationRule
from vision_worker.types import BoundingBox, Detection, Track

ZONE = ZoneConfig(
    zone_id="zone-1",
    name="Loading Dock",
    normalized_polygon=[(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)],
    dwell_time_seconds=0.0,  # trigger immediately for this test
    cooldown_seconds=60.0,
    severity="high",
)


def _dummy_source() -> FrameSource:
    return FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri="unused.mp4"))


def _person_track(track_id: int, x: float, y: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="person",
        box=BoundingBox(x - 10, y - 50, x + 10, y),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def _bag_track(track_id: int, x: float, y: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="backpack",
        box=BoundingBox(x - 10, y - 20, x + 10, y),
        confidence=0.85,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def test_intrusion_rule_triggers_callback_with_correct_event_shape():
    received: list = []

    def on_trigger(event, snapshot):
        received.append((event, snapshot))

    worker = CameraWorker(
        camera_id="cam-1",
        source=_dummy_source(),
        detector=None,
        zone_rules=[ZoneIntrusionRule(ZONE)],
        on_rule_triggered=on_trigger,
    )

    # A person inside the right half of the frame (the zone).
    tracks = [_person_track(1, 800, 500)]
    worker._evaluate_rules(
        tracks, frame_width=1000, frame_height=1000, now=0.0, snapshot=b"jpeg-bytes"
    )

    assert len(received) == 1
    event, snapshot = received[0]
    assert event.category == "intrusion"
    assert event.camera_id == "cam-1"
    assert event.track_ids == [1]
    assert event.zone_id == "zone-1"
    assert event.zone_name == "Loading Dock"
    assert event.severity == "high"
    assert "dwell_seconds" in event.evidence
    assert snapshot == b"jpeg-bytes"
    assert event.dedup_key == "intrusion:cam-1:zone-1:1"


def test_abandoned_object_rule_triggers_callback():
    received: list = []

    worker = CameraWorker(
        camera_id="cam-2",
        source=_dummy_source(),
        detector=None,
        abandoned_object_rule=AbandonedObjectRule(
            AbandonedObjectConfig(stationary_seconds=10.0, owner_proximity_px=100.0)
        ),
        on_rule_triggered=lambda ev, snap: received.append(ev),
    )

    tracks = [_bag_track(1, 500, 500)]
    worker._evaluate_rules(tracks, frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x")
    worker._evaluate_rules(tracks, frame_width=1000, frame_height=1000, now=11.0, snapshot=b"x")

    assert len(received) == 1
    assert received[0].category == "abandoned_object"
    assert received[0].evidence["object_class"] == "backpack"


def test_no_rules_configured_never_calls_callback():
    received: list = []
    worker = CameraWorker(
        camera_id="cam-3",
        source=_dummy_source(),
        detector=None,
        on_rule_triggered=lambda ev, snap: received.append(ev),
    )
    worker._evaluate_rules(
        [_person_track(1, 800, 500)], frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x"
    )
    assert received == []


def test_rule_exception_is_caught_and_does_not_propagate():
    """A broken rule must never crash the inference loop."""

    class BrokenRule:
        def evaluate(self, *args, **kwargs):
            raise RuntimeError("boom")

    worker = CameraWorker(
        camera_id="cam-4",
        source=_dummy_source(),
        detector=None,
        zone_rules=[BrokenRule()],  # type: ignore[list-item]
        on_rule_triggered=lambda ev, snap: None,
    )
    # Must not raise.
    worker._evaluate_rules(
        [_person_track(1, 800, 500)], frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x"
    )


def test_callback_exception_does_not_propagate():
    def broken_callback(event, snapshot):
        raise RuntimeError("callback exploded")

    worker = CameraWorker(
        camera_id="cam-5",
        source=_dummy_source(),
        detector=None,
        zone_rules=[ZoneIntrusionRule(ZONE)],
        on_rule_triggered=broken_callback,
    )
    # Must not raise even though the callback itself throws.
    worker._evaluate_rules(
        [_person_track(1, 800, 500)], frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x"
    )


def test_aggressive_motion_triggers_callback_with_correct_event_shape():
    received: list = []

    worker = CameraWorker(
        camera_id="cam-6",
        source=_dummy_source(),
        detector=None,
        aggressive_motion_rule=AggressiveMotionRule(
            AggressiveMotionConfig(min_consecutive_frames=1, motion_threshold_px_per_frame=10.0)
        ),
        on_rule_triggered=lambda ev, snap: received.append(ev),
    )

    person_a = Track(
        track_id=1,
        class_name="person",
        box=BoundingBox(90, 50, 110, 100),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
        footpoint_history=[(100, 100), (150, 100)],
    )
    person_b = Track(
        track_id=2,
        class_name="person",
        box=BoundingBox(140, 50, 160, 100),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
        footpoint_history=[(150, 100), (200, 100)],
    )
    worker._evaluate_rules(
        [person_a, person_b], frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x"
    )

    assert len(received) == 1
    event = received[0]
    assert event.category == "aggressive_motion"
    assert set(event.track_ids) == {1, 2}
    assert "consecutive_frames" in event.evidence


def test_weapon_confirmation_triggers_callback_with_correct_event_shape():
    received: list = []

    worker = CameraWorker(
        camera_id="cam-7",
        source=_dummy_source(),
        detector=None,
        weapon_confirmation_rule=WeaponConfirmationRule(
            WeaponConfirmationConfig(min_consecutive_frames=1)
        ),
        on_rule_triggered=lambda ev, snap: received.append(ev),
    )

    weapon_detection = Detection(
        box=BoundingBox(400, 400, 440, 460), class_id=0, class_name="pistol", confidence=0.8
    )
    worker._evaluate_rules(
        [],
        frame_width=1000,
        frame_height=1000,
        now=0.0,
        snapshot=b"x",
        weapon_detections=[weapon_detection],
    )

    assert len(received) == 1
    event = received[0]
    assert event.category == "weapon"
    assert event.evidence["weapon_class"] == "pistol"
    assert event.severity == "critical"


def test_no_weapon_detections_never_calls_callback():
    received: list = []
    worker = CameraWorker(
        camera_id="cam-8",
        source=_dummy_source(),
        detector=None,
        weapon_confirmation_rule=WeaponConfirmationRule(),
        on_rule_triggered=lambda ev, snap: received.append(ev),
    )
    worker._evaluate_rules(
        [], frame_width=1000, frame_height=1000, now=0.0, snapshot=b"x", weapon_detections=[]
    )
    assert received == []
