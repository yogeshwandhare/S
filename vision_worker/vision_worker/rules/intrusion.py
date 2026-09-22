"""Restricted-zone intrusion rule.

Tests a tracked person's footpoint (bottom-center of their bounding box --
their ground contact point, not head/torso centroid) against an
operator-drawn polygon. Requires the track to remain inside the zone for a
configurable dwell time before triggering, and enforces a cooldown so a
single continuous intrusion doesn't fire repeatedly every frame.
"""

from __future__ import annotations

from dataclasses import dataclass

from vision_worker.rules.geometry import denormalize_polygon, point_in_polygon
from vision_worker.types import Track


@dataclass
class ZoneConfig:
    zone_id: str
    name: str
    # Normalized (0.0-1.0) polygon vertices, as stored in the database.
    normalized_polygon: list[tuple[float, float]]
    dwell_time_seconds: float = 1.0
    cooldown_seconds: float = 60.0
    severity: str = "medium"
    enabled: bool = True


@dataclass(frozen=True)
class IntrusionEvent:
    zone_id: str
    zone_name: str
    track_id: int
    severity: str
    dwell_seconds: float


@dataclass
class _TrackZoneState:
    entered_at: float | None = None
    last_triggered_at: float | None = None
    triggered_for_current_visit: bool = False


class ZoneIntrusionRule:
    """Stateful evaluator for exactly one zone. Create one instance per
    configured zone; call `evaluate()` once per processed frame with the
    frame's current tracks and a monotonic timestamp."""

    def __init__(self, zone: ZoneConfig) -> None:
        self.zone = zone
        self._track_state: dict[int, _TrackZoneState] = {}

    def evaluate(
        self, tracks: list[Track], frame_width: int, frame_height: int, now: float
    ) -> list[IntrusionEvent]:
        if not self.zone.enabled:
            return []

        polygon_px = denormalize_polygon(self.zone.normalized_polygon, frame_width, frame_height)
        events: list[IntrusionEvent] = []
        seen_track_ids: set[int] = set()

        for track in tracks:
            if track.class_name != "person":
                continue  # only people can "intrude" -- not bags, vehicles, etc.

            seen_track_ids.add(track.track_id)
            state = self._track_state.setdefault(track.track_id, _TrackZoneState())
            inside = point_in_polygon(track.box.footpoint, polygon_px)

            if not inside:
                # Left the zone (or was never in it) -- reset dwell tracking
                # so a future re-entry is evaluated as a fresh visit.
                state.entered_at = None
                state.triggered_for_current_visit = False
                continue

            if state.entered_at is None:
                state.entered_at = now

            dwell = now - state.entered_at
            if dwell < self.zone.dwell_time_seconds:
                continue

            if state.triggered_for_current_visit:
                continue  # already fired for this continuous visit

            if (
                state.last_triggered_at is not None
                and now - state.last_triggered_at < self.zone.cooldown_seconds
            ):
                continue  # still in cooldown from a previous visit

            state.triggered_for_current_visit = True
            state.last_triggered_at = now
            events.append(
                IntrusionEvent(
                    zone_id=self.zone.zone_id,
                    zone_name=self.zone.name,
                    track_id=track.track_id,
                    severity=self.zone.severity,
                    dwell_seconds=dwell,
                )
            )

        # Forget tracks that have disappeared entirely (left the frame, not
        # just the zone) so state doesn't grow without bound over a long
        # camera session.
        stale_ids = set(self._track_state.keys()) - seen_track_ids
        for track_id in stale_ids:
            del self._track_state[track_id]

        return events
