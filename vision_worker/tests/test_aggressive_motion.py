"""Aggressive-motion rule tests. Synthetic track fixtures only."""

from __future__ import annotations

from vision_worker.rules.aggressive_motion import AggressiveMotionConfig, AggressiveMotionRule
from vision_worker.types import BoundingBox, Track

CONFIG = AggressiveMotionConfig(
    proximity_px=200.0,
    motion_threshold_px_per_frame=25.0,
    min_consecutive_frames=3,
    cooldown_seconds=30.0,
)


def _person(track_id: int, footpoints: list[tuple[float, float]]) -> Track:
    x, y = footpoints[-1]
    return Track(
        track_id=track_id,
        class_name="person",
        box=BoundingBox(x - 10, y - 50, x + 10, y),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
        footpoint_history=list(footpoints),
    )


def test_no_events_with_fewer_than_two_people():
    rule = AggressiveMotionRule(CONFIG)
    events = rule.evaluate([_person(1, [(100, 100), (140, 100)])], now=0.0)
    assert events == []


def test_two_stationary_people_never_trigger():
    rule = AggressiveMotionRule(CONFIG)
    for t in range(5):
        events = rule.evaluate(
            [
                _person(1, [(100, 100), (101, 100)]),
                _person(2, [(120, 100), (121, 100)]),
            ],
            now=float(t),
        )
        assert events == []


def test_two_people_far_apart_moving_fast_never_trigger():
    rule = AggressiveMotionRule(CONFIG)
    for t in range(5):
        events = rule.evaluate(
            [
                _person(1, [(0, 0), (50, 0)]),
                _person(2, [(900, 900), (950, 900)]),
            ],
            now=float(t),
        )
        assert events == []


def test_one_person_moving_fast_alone_never_triggers():
    rule = AggressiveMotionRule(CONFIG)
    for t in range(5):
        events = rule.evaluate([_person(1, [(0, 0), (50, 0), (100, 0)])], now=float(t))
        assert events == []


def test_sustained_close_rapid_motion_triggers_after_min_frames():
    rule = AggressiveMotionRule(CONFIG)
    positions_a = [(100, 100)]
    positions_b = [(150, 100)]

    all_events = []
    for i in range(6):
        positions_a.append((100 + i * 40, 100))
        positions_b.append((150 + i * 40, 100))
        events = rule.evaluate([_person(1, positions_a), _person(2, positions_b)], now=float(i))
        all_events.extend(events)

    assert len(all_events) >= 1
    assert all_events[0].track_ids == (1, 2)
    assert all_events[0].consecutive_frames == CONFIG.min_consecutive_frames


def test_single_fast_frame_does_not_trigger():
    rule = AggressiveMotionRule(CONFIG)
    rule.evaluate([_person(1, [(100, 100)]), _person(2, [(150, 100)])], now=0.0)
    events = rule.evaluate(
        [_person(1, [(100, 100), (140, 100)]), _person(2, [(150, 100), (190, 100)])], now=1.0
    )
    assert events == []
    events = rule.evaluate(
        [_person(1, [(140, 100), (141, 100)]), _person(2, [(190, 100), (191, 100)])], now=2.0
    )
    assert events == []


def test_motion_interrupted_resets_consecutive_counter():
    rule = AggressiveMotionRule(CONFIG)
    pa, pb = [(0, 100)], [(50, 100)]

    for i in range(2):
        pa.append((i * 40 + 40, 100))
        pb.append((i * 40 + 90, 100))
        rule.evaluate([_person(1, pa), _person(2, pb)], now=float(i))

    pa.append(pa[-1])
    pb.append(pb[-1])
    rule.evaluate([_person(1, pa), _person(2, pb)], now=2.0)

    triggered = False
    for i in range(3, 3 + CONFIG.min_consecutive_frames):
        pa.append((pa[-1][0] + 40, 100))
        pb.append((pb[-1][0] + 40, 100))
        events = rule.evaluate([_person(1, pa), _person(2, pb)], now=float(i))
        if events:
            triggered = True
            assert events[0].consecutive_frames == CONFIG.min_consecutive_frames
            break
    assert triggered


def test_does_not_retrigger_within_cooldown():
    rule = AggressiveMotionRule(CONFIG)
    pa, pb = [(0, 100)], [(50, 100)]
    all_events = []
    for i in range(8):
        pa.append((pa[-1][0] + 40, 100))
        pb.append((pb[-1][0] + 40, 100))
        events = rule.evaluate([_person(1, pa), _person(2, pb)], now=float(i))
        all_events.extend(events)
    assert len(all_events) == 1


def test_backpack_and_person_never_form_a_pair():
    rule = AggressiveMotionRule(CONFIG)
    bag = Track(
        track_id=2,
        class_name="backpack",
        box=BoundingBox(140, 80, 160, 100),
        confidence=0.8,
        first_seen_frame=1,
        last_seen_frame=1,
        footpoint_history=[(150, 100), (190, 100)],
    )
    for t in range(5):
        events = rule.evaluate([_person(1, [(100, 100), (140 + t * 40, 100)]), bag], now=float(t))
        assert events == []
