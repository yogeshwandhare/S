"""Weapon confirmation rule tests. Synthetic detection fixtures only."""

from __future__ import annotations

from vision_worker.rules.weapon_confirmation import WeaponConfirmationConfig, WeaponConfirmationRule
from vision_worker.types import BoundingBox, Detection

CONFIG = WeaponConfirmationConfig(
    min_consecutive_frames=3, match_distance_px=100.0, cooldown_seconds=60.0, severity="critical"
)


def _weapon_det(class_name: str, x: float, y: float, conf: float = 0.7) -> Detection:
    return Detection(
        box=BoundingBox(x - 15, y - 15, x + 15, y + 15),
        class_id=0,
        class_name=class_name,
        confidence=conf,
    )


def _phone_det(x: float, y: float) -> Detection:
    return Detection(
        box=BoundingBox(x - 10, y - 10, x + 10, y + 10),
        class_id=1,
        class_name="smartphone",
        confidence=0.9,
    )


def test_single_frame_detection_does_not_confirm():
    rule = WeaponConfirmationRule(CONFIG)
    events = rule.evaluate([_weapon_det("pistol", 100, 100)], now=0.0)
    assert events == []


def test_sustained_detection_confirms_after_threshold():
    rule = WeaponConfirmationRule(CONFIG)
    rule.evaluate([_weapon_det("pistol", 100, 100)], now=0.0)
    rule.evaluate([_weapon_det("pistol", 102, 101)], now=1.0)
    events = rule.evaluate([_weapon_det("pistol", 101, 103)], now=2.0)
    assert len(events) == 1
    assert events[0].class_name == "pistol"
    assert events[0].consecutive_frames == 3


def test_non_weapon_classes_never_confirm():
    rule = WeaponConfirmationRule(CONFIG)
    for t in range(5):
        events = rule.evaluate([_phone_det(100, 100)], now=float(t))
        assert events == []


def test_detection_disappearing_resets_consecutive_count():
    rule = WeaponConfirmationRule(CONFIG)
    rule.evaluate([_weapon_det("knife", 200, 200)], now=0.0)
    rule.evaluate([_weapon_det("knife", 201, 201)], now=1.0)
    rule.evaluate([], now=2.0)
    rule.evaluate([_weapon_det("knife", 200, 200)], now=3.0)
    events = rule.evaluate([_weapon_det("knife", 201, 200)], now=4.0)
    assert events == []


def test_detection_far_away_counts_as_new_candidate():
    rule = WeaponConfirmationRule(CONFIG)
    rule.evaluate([_weapon_det("pistol", 100, 100)], now=0.0)
    rule.evaluate([_weapon_det("pistol", 101, 100)], now=1.0)
    events = rule.evaluate([_weapon_det("pistol", 900, 900)], now=2.0)
    assert events == []


def test_does_not_retrigger_within_cooldown():
    rule = WeaponConfirmationRule(CONFIG)
    all_events = []
    for t in range(8):
        events = rule.evaluate([_weapon_det("pistol", 100 + t, 100)], now=float(t))
        all_events.extend(events)
    assert len(all_events) == 1


def test_two_simultaneous_weapon_candidates_tracked_independently():
    rule = WeaponConfirmationRule(CONFIG)
    all_events = []
    for t in range(4):
        events = rule.evaluate(
            [_weapon_det("pistol", 100 + t, 100), _weapon_det("knife", 800 + t, 800)], now=float(t)
        )
        all_events.extend(events)
    class_names = {e.class_name for e in all_events}
    assert class_names == {"pistol", "knife"}
