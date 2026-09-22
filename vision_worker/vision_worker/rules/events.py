"""The single event shape every rule's trigger gets normalized into before
being handed to the camera worker's `on_rule_triggered` callback.

Keeping this in vision_worker (rather than defining it in the backend)
means the rule engine stays fully independent of any database or web
framework -- the callback that turns this into a persisted `Incident` row
lives entirely on the backend side (see app/services/incident_service.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RuleTriggerEvent:
    category: str  # "intrusion" | "abandoned_object"
    camera_id: str
    track_ids: list[int]
    severity: str
    occurred_at: datetime
    zone_id: str | None = None
    zone_name: str | None = None
    # Free-form, JSON-serializable evidence (dwell_seconds, stationary_seconds,
    # etc.) -- kept as a plain dict rather than a fixed schema so different
    # rule types can attach whatever's relevant without a shared base class.
    evidence: dict = field(default_factory=dict)
    # A stable key for deduplication: the same (category, camera, zone,
    # track) combination within a short window should not create two
    # incidents even if something upstream double-fires.
    dedup_key: str = ""

    def __post_init__(self) -> None:
        if not self.dedup_key:
            track_part = "-".join(str(t) for t in sorted(self.track_ids))
            zone_part = self.zone_id or "none"
            object.__setattr__(
                self, "dedup_key", f"{self.category}:{self.camera_id}:{zone_part}:{track_part}"
            )
