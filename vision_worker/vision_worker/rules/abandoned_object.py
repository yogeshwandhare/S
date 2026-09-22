"""Abandoned/unattended object rule.

Tracks bags/luggage over time. Triggers a candidate event when an object
has remained stationary beyond a configurable threshold AND no person
track is within a configurable proximity radius -- i.e. it looks
unattended, not merely that it hasn't moved (someone could be sitting
right next to their bag).

This produces a *candidate* event, never a claim that the object is
dangerous -- see IncidentCategory.ABANDONED_OBJECT's handling in the
incident service, which always surfaces it for human review.
"""

from __future__ import annotations

from dataclasses import dataclass

from vision_worker.rules.geometry import euclidean_distance
from vision_worker.types import Track

#: Object classes this rule considers "luggage-like". Read from whatever
#: the active detector's class_names actually contains -- if a checkpoint
#: doesn't support these classes, this rule simply never fires for it,
#: rather than assuming they exist.
LUGGAGE_CLASSES = frozenset({"backpack", "handbag", "suitcase"})


@dataclass
class AbandonedObjectConfig:
    stationary_seconds: float = 60.0
    # How far (in pixels, at the frame's native resolution) an object's
    # footpoint may drift between frames and still count as "stationary".
    movement_tolerance_px: float = 15.0
    # How close (in pixels) a person must be to count as a plausible owner.
    owner_proximity_px: float = 150.0
    cooldown_seconds: float = 300.0


@dataclass(frozen=True)
class AbandonedObjectEvent:
    track_id: int
    class_name: str
    stationary_seconds: float


@dataclass
class _ObjectState:
    anchor_position: tuple[float, float]
    anchor_time: float
    last_triggered_at: float | None = None
    triggered_for_current_stationary_period: bool = False


class AbandonedObjectRule:
    """Stateful evaluator across all cameras' luggage-class tracks. Create
    one instance per camera; call `evaluate()` once per processed frame."""

    def __init__(self, config: AbandonedObjectConfig | None = None) -> None:
        self.config = config or AbandonedObjectConfig()
        self._object_state: dict[int, _ObjectState] = {}

    def evaluate(self, tracks: list[Track], now: float) -> list[AbandonedObjectEvent]:
        people = [t for t in tracks if t.class_name == "person"]
        objects = [t for t in tracks if t.class_name in LUGGAGE_CLASSES]

        events: list[AbandonedObjectEvent] = []
        seen_ids: set[int] = set()

        for obj in objects:
            seen_ids.add(obj.track_id)
            position = obj.box.footpoint
            state = self._object_state.get(obj.track_id)

            if state is None:
                self._object_state[obj.track_id] = _ObjectState(
                    anchor_position=position, anchor_time=now
                )
                continue

            moved = euclidean_distance(position, state.anchor_position)
            if moved > self.config.movement_tolerance_px:
                # Object relocated -- restart the stationarity clock from here.
                state.anchor_position = position
                state.anchor_time = now
                state.triggered_for_current_stationary_period = False
                continue

            stationary_for = now - state.anchor_time
            if stationary_for < self.config.stationary_seconds:
                continue

            if state.triggered_for_current_stationary_period:
                continue

            if (
                state.last_triggered_at is not None
                and now - state.last_triggered_at < self.config.cooldown_seconds
            ):
                continue

            nearest_person_distance = min(
                (euclidean_distance(position, p.box.footpoint) for p in people),
                default=float("inf"),
            )
            if nearest_person_distance <= self.config.owner_proximity_px:
                continue  # a plausible owner is still nearby -- not abandoned

            state.triggered_for_current_stationary_period = True
            state.last_triggered_at = now
            events.append(
                AbandonedObjectEvent(
                    track_id=obj.track_id,
                    class_name=obj.class_name,
                    stationary_seconds=stationary_for,
                )
            )

        stale_ids = set(self._object_state.keys()) - seen_ids
        for track_id in stale_ids:
            del self._object_state[track_id]

        return events
