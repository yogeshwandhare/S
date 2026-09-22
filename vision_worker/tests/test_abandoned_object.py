"""Abandoned-object rule tests. Synthetic track fixtures only."""

from __future__ import annotations

from vision_worker.rules.abandoned_object import (
    AbandonedObjectConfig,
    AbandonedObjectRule,
)
from vision_worker.types import BoundingBox, Track

CONFIG = AbandonedObjectConfig(
    stationary_seconds=60.0,
    movement_tolerance_px=15.0,
    owner_proximity_px=150.0,
    cooldown_seconds=300.0,
)


def _bag_at(track_id: int, x: float, y: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="backpack",
        box=BoundingBox(x1=x - 10, y1=y - 20, x2=x + 10, y2=y),
        confidence=0.85,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def _person_at(track_id: int, x: float, y: float) -> Track:
    return Track(
        track_id=track_id,
        class_name="person",
        box=BoundingBox(x1=x - 10, y1=y - 50, x2=x + 10, y2=y),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
    )


def test_bag_alone_and_stationary_triggers_after_threshold():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    events = rule.evaluate([_bag_at(1, 500, 500)], now=61.0)
    assert len(events) == 1
    assert events[0].track_id == 1
    assert events[0].class_name == "backpack"


def test_bag_alone_does_not_trigger_before_threshold():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    events = rule.evaluate([_bag_at(1, 500, 500)], now=30.0)
    assert events == []


def test_bag_with_nearby_owner_never_triggers():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500), _person_at(2, 520, 500)], now=0.0)
    events = rule.evaluate([_bag_at(1, 500, 500), _person_at(2, 520, 500)], now=61.0)
    assert events == []  # person is only 20px away, well within 150px proximity


def test_bag_triggers_once_owner_walks_away():
    rule = AbandonedObjectRule(CONFIG)
    # Owner right next to the bag initially.
    rule.evaluate([_bag_at(1, 500, 500), _person_at(2, 520, 500)], now=0.0)
    # Owner walks far away; bag hasn't moved.
    rule.evaluate([_bag_at(1, 500, 500), _person_at(2, 900, 900)], now=30.0)
    events = rule.evaluate([_bag_at(1, 500, 500), _person_at(2, 900, 900)], now=61.0)
    assert len(events) == 1


def test_small_jitter_within_tolerance_still_counts_as_stationary():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    # Small movement (5px) -- within the 15px tolerance -- should not reset the clock.
    rule.evaluate([_bag_at(1, 503, 502)], now=30.0)
    events = rule.evaluate([_bag_at(1, 500, 500)], now=61.0)
    assert len(events) == 1


def test_object_relocation_resets_stationarity_clock():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    # Moves 200px -- well beyond tolerance -- clock resets.
    rule.evaluate([_bag_at(1, 700, 500)], now=30.0)
    # Only 31s have passed since the reset at t=30 -- must not trigger yet.
    events = rule.evaluate([_bag_at(1, 700, 500)], now=61.0)
    assert events == []
    # But 61s after the reset, it should.
    events = rule.evaluate([_bag_at(1, 700, 500)], now=91.0)
    assert len(events) == 1


def test_does_not_retrigger_within_cooldown():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    first = rule.evaluate([_bag_at(1, 500, 500)], now=61.0)
    assert len(first) == 1
    second = rule.evaluate([_bag_at(1, 500, 500)], now=90.0)
    assert second == []  # within the 300s cooldown


def test_only_luggage_classes_are_considered():
    rule = AbandonedObjectRule(CONFIG)
    car = Track(
        track_id=1,
        class_name="car",
        box=BoundingBox(490, 480, 510, 500),
        confidence=0.9,
        first_seen_frame=1,
        last_seen_frame=1,
    )
    rule.evaluate([car], now=0.0)
    events = rule.evaluate([car], now=61.0)
    assert events == []


def test_object_state_forgotten_once_object_disappears():
    rule = AbandonedObjectRule(CONFIG)
    rule.evaluate([_bag_at(1, 500, 500)], now=0.0)
    assert 1 in rule._object_state
    rule.evaluate([], now=1.0)
    assert 1 not in rule._object_state
