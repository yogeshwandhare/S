from __future__ import annotations

import json
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    camera_id: uuid.UUID
    category: IncidentCategory
    severity: IncidentSeverity
    status: IncidentStatus
    model_name: str | None
    ai_confidence: float | None
    snapshot_path: str | None
    assigned_operator_id: uuid.UUID | None
    review_notes: str | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    human_confirmed: bool | None
    event_started_at: datetime
    event_ended_at: datetime | None
    created_at: datetime

    # Parsed from evidence_json for the API response -- e.g.
    # {"dwell_seconds": 3.2, "zone_name": "Loading Dock"}
    evidence: dict = Field(default_factory=dict)
    track_ids: list[int] = Field(default_factory=list)

    @classmethod
    def from_orm_incident(cls, incident) -> IncidentRead:
        return cls(
            id=incident.id,
            camera_id=incident.camera_id,
            category=incident.category,
            severity=incident.severity,
            status=incident.status,
            model_name=incident.model_name,
            ai_confidence=incident.ai_confidence,
            snapshot_path=incident.snapshot_path,
            assigned_operator_id=incident.assigned_operator_id,
            review_notes=incident.review_notes,
            acknowledged_at=incident.acknowledged_at,
            resolved_at=incident.resolved_at,
            human_confirmed=incident.human_confirmed,
            event_started_at=incident.event_started_at,
            event_ended_at=incident.event_ended_at,
            created_at=incident.created_at,
            evidence=json.loads(incident.evidence_json) if incident.evidence_json else {},
            track_ids=json.loads(incident.track_ids_json) if incident.track_ids_json else [],
        )


class IncidentReviewUpdate(BaseModel):
    """Fields an operator can change when reviewing an incident."""

    status: IncidentStatus | None = None
    review_notes: str | None = None
    human_confirmed: bool | None = None
    assigned_operator_id: uuid.UUID | None = None


class IncidentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    detail: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime
