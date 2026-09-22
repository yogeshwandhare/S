"""Aggressive-motion heuristic.

There is no validated fight/violence classifier in this project (see
docs/MODEL_REGISTRY.md for what that would take -- a temporal action
model with real, licensed training data this project does not have).
Per the project brief, until one exists, this heuristic flags candidate
events as "Aggressive motion -- review required", never "Fight confirmed".

The signal: two or more tracked people in close proximity, each moving
rapidly frame-to-frame, sustained across several consecutive frames (not
a single fast movement -- a person startled or jogging past someone else
for one frame should not trigger this). This will also fire on dancing,
contact sports, rough play, and dense crowd movement -- that is an
accepted, documented limitation of a motion-only heuristic (see
docs/LIMITATIONS.md), which is exactly why this always requires human
review rather than asserting a fight occurred.

Velocity is measured in pixels-per-processed-frame, not pixels-per-second
-- since the camera worker's inference rate is configurable per camera,
`motion_threshold` should be tuned per deployment rather than treated as
an absolute, physically calibrated speed.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from vision_worker.rules.geometry import euclidean_distance
from vision_worker.types import Track


@dataclass
class AggressiveMotionConfig:
    proximity_px: float = 200.0
    motion_threshold_px_per_frame: float = 25.0
    min_consecutive_frames: int = 5
    cooldown_seconds: float = 30.0
    severity: str = "medium"


@dataclass(frozen=True)
class AggressiveMotionEvent:
    track_ids: tuple[int, ...]
    severity: str
    consecutive_frames: int


@dataclass
class _PairState:
    consecutive_frames: int = 0
    last_triggered_at: float | None = None


def _recent_displacement(track: Track) -> float | None:
    """Distance moved between the two most recent footpoint observations,
    or None if there isn't enough history yet to tell."""
    if len(track.footpoint_history) < 2:
        return None
    return euclidean_distance(track.footpoint_history[-1], track.footpoint_history[-2])


class AggressiveMotionRule:
    """Stateful evaluator for one camera. Call `evaluate()` once per
    processed frame with that frame's current tracks."""

    def __init__(self, config: AggressiveMotionConfig | None = None) -> None:
        self.config = config or AggressiveMotionConfig()
        self._pair_state: dict[frozenset[int], _PairState] = {}

    def evaluate(self, tracks: list[Track], now: float) -> list[AggressiveMotionEvent]:
        people = [t for t in tracks if t.class_name == "person"]
        events: list[AggressiveMotionEvent] = []
        active_pairs: set[frozenset[int]] = set()

        for track_a, track_b in combinations(people, 2):
            distance = euclidean_distance(track_a.box.footpoint, track_b.box.footpoint)
            if distance > self.config.proximity_px:
                continue

            speed_a = _recent_displacement(track_a)
            speed_b = _recent_displacement(track_b)
            if speed_a is None or speed_b is None:
                continue
            if (
                speed_a < self.config.motion_threshold_px_per_frame
                or speed_b < self.config.motion_threshold_px_per_frame
            ):
                continue

            pair_key = frozenset({track_a.track_id, track_b.track_id})
            active_pairs.add(pair_key)
            state = self._pair_state.setdefault(pair_key, _PairState())
            state.consecutive_frames += 1

            if state.consecutive_frames < self.config.min_consecutive_frames:
                continue
            if (
                state.last_triggered_at is not None
                and now - state.last_triggered_at < self.config.cooldown_seconds
            ):
                continue

            state.last_triggered_at = now
            events.append(
                AggressiveMotionEvent(
                    track_ids=tuple(sorted(pair_key)),
                    severity=self.config.severity,
                    consecutive_frames=state.consecutive_frames,
                )
            )

        # Reset the streak for any pair that didn't qualify this frame --
        # this is what makes "sustained" mean *consecutive*, not cumulative.
        for pair_key in list(self._pair_state.keys()):
            if pair_key not in active_pairs:
                del self._pair_state[pair_key]

        return events
