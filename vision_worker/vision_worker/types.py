"""Shared data types passed between the detector, tracker, and rule engine.

Kept dependency-light (stdlib dataclasses only) so unit tests can construct
synthetic detections/tracks without needing OpenCV, PyTorch, or a real
model loaded -- see the project brief's requirement that rule-engine tests
use synthetic fixtures, not live inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoundingBox:
    """Pixel-space box in `x1, y1, x2, y2` (top-left, bottom-right) form."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def footpoint(self) -> tuple[float, float]:
        """Bottom-center of the box -- used as the ground-contact anchor for
        zone-intrusion testing (a person's feet, not their head/torso
        centroid, are what should be tested against a floor-plane polygon)."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    def iou(self, other: BoundingBox) -> float:
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter_w = max(0.0, ix2 - ix1)
        inter_h = max(0.0, iy2 - iy1)
        inter_area = inter_w * inter_h
        union_area = self.area + other.area - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area


@dataclass(frozen=True)
class Detection:
    """A single object detection in one frame, in the detector's own class
    vocabulary (see each detector adapter's `class_names`)."""

    box: BoundingBox
    class_id: int
    class_name: str
    confidence: float


@dataclass
class Track:
    """A tracked object, persisted across frames by the tracker."""

    track_id: int
    class_name: str
    box: BoundingBox
    confidence: float
    first_seen_frame: int
    last_seen_frame: int
    # Recent footpoint history, oldest first -- used by stationarity checks
    # (abandoned-object detection) and dwell-time checks (intrusion).
    footpoint_history: list[tuple[float, float]] = field(default_factory=list)
    missed_frames: int = 0
