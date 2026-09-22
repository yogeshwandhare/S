"""Zone intrusion rule tests. All tracks here are synthetic test fixtures,
per the project brief's requirement -- no video or model inference."""

from __future__ import annotations

from vision_worker.rules.intrusion import ZoneConfig, ZoneIntrusionRule
from vision_worker.types import BoundingBox, Track

# A zone covering the right half of the frame, in normalized coordinates.
RIGHT_HALF_ZONE = ZoneConfig(
    zone_id="zone-1",
    name="Restricted Area",
    normalized_polygon=[(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)],
    dwell_time_seconds=2.0,
    cooldown_seconds=10.0,
    severity="high",
)

FRAME_W, FRAME_H = 1000, 1000


def _person_at(track_id: int, x: float, y: float) -> Track:
    """A person track whose footpoint lands at pixel (x, y)."""
    return Track(
        track_id=track_id,
        class_name="person",
        box=BoundingBox(x1=x - 10, y1=y - 50, x2=x + 10, y2=y),  # footpoint = (x, y)
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def _bag_at(track_id: int, x: float, y: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="backpack",
        box=BoundingBox(x1=x - 10, y1=y - 20, x2=x + 10, y2=y),
        confidence=0.8,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def test_person_outside_zone_never_triggers():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    for t in range(0, 20):
        events = rule.evaluate([_person_at(1, 200, 500)], FRAME_W, FRAME_H, now=float(t))
        assert events == []


def test_person_inside_zone_does_not_trigger_before_dwell_time():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    events = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    assert events == []
    events = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=1.0)
    assert events == []


def test_person_inside_zone_triggers_after_dwell_time():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    events = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=2.5)
    assert len(events) == 1
    assert events[0].track_id == 1
    assert events[0].zone_id == "zone-1"
    assert events[0].severity == "high"
    assert events[0].dwell_seconds == 2.5


def test_does_not_retrigger_repeatedly_for_same_continuous_visit():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    first = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=2.5)
    assert len(first) == 1
    second = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=3.0)
    third = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=5.0)
    assert second == []
    assert third == []


def test_leaving_and_reentering_within_cooldown_does_not_retrigger():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=2.5)

    rule.evaluate([_person_at(1, 200, 500)], FRAME_W, FRAME_H, now=3.0)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=4.0)
    events = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=6.5)
    assert events == []


def test_leaving_and_reentering_after_cooldown_retriggers():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    first = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=2.5)
    assert len(first) == 1

    rule.evaluate([_person_at(1, 200, 500)], FRAME_W, FRAME_H, now=3.0)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=20.0)
    second = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=22.5)
    assert len(second) == 1


def test_non_person_tracks_never_trigger_intrusion():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    for t in range(0, 10):
        events = rule.evaluate([_bag_at(1, 800, 500)], FRAME_W, FRAME_H, now=float(t))
        assert events == []


def test_disabled_zone_never_triggers():
    disabled_zone = ZoneConfig(
        zone_id="zone-2",
        name="Disabled Zone",
        normalized_polygon=RIGHT_HALF_ZONE.normalized_polygon,
        dwell_time_seconds=0.0,
        enabled=False,
    )
    rule = ZoneIntrusionRule(disabled_zone)
    events = rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=10.0)
    assert events == []


def test_multiple_people_tracked_independently():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500), _person_at(2, 200, 500)], FRAME_W, FRAME_H, now=0.0)
    events = rule.evaluate(
        [_person_at(1, 800, 500), _person_at(2, 200, 500)], FRAME_W, FRAME_H, now=2.5
    )
    assert len(events) == 1
    assert events[0].track_id == 1


def test_track_state_is_forgotten_once_track_disappears():
    rule = ZoneIntrusionRule(RIGHT_HALF_ZONE)
    rule.evaluate([_person_at(1, 800, 500)], FRAME_W, FRAME_H, now=0.0)
    assert 1 in rule._track_state
    rule.evaluate([], FRAME_W, FRAME_H, now=1.0)
    assert 1 not in rule._track_state
