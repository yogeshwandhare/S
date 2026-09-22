from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any_role, require_operator_or_admin
from app.models.enums import IncidentCategory, IncidentStatus
from app.models.incident import Incident, IncidentEvent
from app.models.user import User
from app.schemas.incident import IncidentEventRead, IncidentRead, IncidentReviewUpdate

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _get_incident_or_404(db: Session, incident_id: uuid.UUID) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    camera_id: uuid.UUID | None = None,
    category: IncidentCategory | None = None,
    status_filter: IncidentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> list[IncidentRead]:
    query = select(Incident).order_by(Incident.created_at.desc())
    if camera_id is not None:
        query = query.where(Incident.camera_id == camera_id)
    if category is not None:
        query = query.where(Incident.category == category)
    if status_filter is not None:
        query = query.where(Incident.status == status_filter)
    query = query.limit(limit).offset(offset)

    incidents = list(db.scalars(query))
    return [IncidentRead.from_orm_incident(i) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> IncidentRead:
    return IncidentRead.from_orm_incident(_get_incident_or_404(db, incident_id))


@router.get("/{incident_id}/timeline", response_model=list[IncidentEventRead])
def get_incident_timeline(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> list[IncidentEvent]:
    _get_incident_or_404(db, incident_id)
    return list(
        db.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at)
        )
    )


@router.get("/{incident_id}/snapshot")
def get_incident_snapshot(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> FileResponse:
    incident = _get_incident_or_404(db, incident_id)
    if not incident.snapshot_path or not os.path.exists(incident.snapshot_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot available for this incident"
        )
    return FileResponse(incident.snapshot_path, media_type="image/jpeg")


@router.patch("/{incident_id}", response_model=IncidentRead)
def review_incident(
    incident_id: uuid.UUID,
    payload: IncidentReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator_or_admin),
) -> IncidentRead:
    """The human-review action: acknowledge, investigate, resolve, mark a
    false positive, add notes, or assign an operator. This is the only
    place `Incident.status` changes after creation, and every change is
    recorded in the incident's own audit timeline."""
    incident = _get_incident_or_404(db, incident_id)
    changes = payload.model_dump(exclude_unset=True)

    new_status = changes.get("status")
    if new_status is not None:
        now = datetime.now(UTC)
        if new_status == IncidentStatus.ACKNOWLEDGED and incident.acknowledged_at is None:
            incident.acknowledged_at = now
        if new_status in (IncidentStatus.RESOLVED, IncidentStatus.FALSE_POSITIVE):
            incident.resolved_at = now
            incident.event_ended_at = incident.event_ended_at or now

    for field, value in changes.items():
        setattr(incident, field, value)

    db.add(
        IncidentEvent(
            incident_id=incident.id,
            actor_user_id=user.id,
            event_type="reviewed",
            detail=str(changes),
        )
    )
    db.commit()
    db.refresh(incident)
    return IncidentRead.from_orm_incident(incident)
