"""Weapon temporal-confirmation rule.

The weapon detector runs as a separate pass from the main object
detector/tracker, so weapon detections don't come with a persistent track
ID the way person/bag detections do. This rule does its own lightweight
spatial matching across frames (nearest detection within a distance
threshold counts as "the same candidate") and requires several consecutive
frames of detection before treating it as confirmed enough to create an
incident -- a single frame's false positive should not become an alert.

Per the project brief, this NEVER produces a "weapon confirmed" claim --
only "possible weapon", always pending human review (see
IncidentCategory.WEAPON's handling in the incident service).
"""

from __future__ import annotations

from dataclasses import dataclass

from vision_worker.rules.geometry import euclidean_distance
from vision_worker.types import Detection

# Class names found in common weapon datasets. Match normalized checkpoint
# labels so the alert rule works with the linked YOLOv8 model's metadata.
_WEAPON_LABELS = frozenset(
    {
        "pistol", "pistols", "knife", "knives", "gun", "guns", "handgun",
        "handguns", "firearm", "firearms", "rifle", "rifles", "shotgun",
        "shotguns", "revolver", "revolvers", "weapon", "weapons",
    }
)


def _is_weapon_label(class_name: str) -> bool:
    normalized = " ".join(class_name.casefold().replace("_", " ").replace("-", " ").split())
    return normalized in _WEAPON_LABELS


@dataclass
class WeaponConfirmationConfig:
    min_consecutive_frames: int = 3
    match_distance_px: float = 100.0
    cooldown_seconds: float = 60.0
    severity: str = "critical"


@dataclass(frozen=True)
class WeaponConfirmedEvent:
    class_name: str
    confidence: float
    severity: str
    consecutive_frames: int


@dataclass
class _Candidate:
    position: tuple[float, float]
    class_name: str
    confidence: float
    consecutive_frames: int = 1
    matched_this_frame: bool = True
    last_triggered_at: float | None = None


class WeaponConfirmationRule:
    def __init__(self, config: WeaponConfirmationConfig | None = None) -> None:
        self.config = config or WeaponConfirmationConfig()
        self._candidates: list[_Candidate] = []

    def evaluate(self, detections: list[Detection], now: float) -> list[WeaponConfirmedEvent]:
        weapon_detections = [d for d in detections if _is_weapon_label(d.class_name)]

        for c in self._candidates:
            c.matched_this_frame = False

        events: list[WeaponConfirmedEvent] = []

        for detection in weapon_detections:
            position = detection.box.center
            match = self._find_nearest_candidate(position, detection.class_name)

            if match is not None:
                match.position = position
                match.confidence = detection.confidence
                match.consecutive_frames += 1
                match.matched_this_frame = True
            else:
                match = _Candidate(
                    position=position,
                    class_name=detection.class_name,
                    confidence=detection.confidence,
                )
                self._candidates.append(match)

            if match.consecutive_frames < self.config.min_consecutive_frames:
                continue
            if (
                match.last_triggered_at is not None
                and now - match.last_triggered_at < self.config.cooldown_seconds
            ):
                continue

            match.last_triggered_at = now
            events.append(
                WeaponConfirmedEvent(
                    class_name=match.class_name,
                    confidence=match.confidence,
                    severity=self.config.severity,
                    consecutive_frames=match.consecutive_frames,
                )
            )

        self._candidates = [c for c in self._candidates if c.matched_this_frame]

        return events

    def _find_nearest_candidate(
        self, position: tuple[float, float], class_name: str
    ) -> _Candidate | None:
        best: _Candidate | None = None
        best_distance = self.config.match_distance_px
        for candidate in self._candidates:
            if candidate.class_name != class_name or candidate.matched_this_frame:
                continue
            distance = euclidean_distance(position, candidate.position)
            if distance <= best_distance:
                best = candidate
                best_distance = distance
        return best
