from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin, require_any_role
from app.models.audit_log import AuditLog
from app.models.camera import Camera, Zone
from app.models.user import User
from app.schemas.zone import ZoneCreate, ZoneRead, ZoneUpdate

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _get_zone_or_404(db: Session, zone_id: uuid.UUID) -> Zone:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


def _reload_camera_zones(request: Request, camera_id: uuid.UUID, db: Session) -> None:
    """Zones are read once when a camera worker starts; changing a zone
    means the running worker needs to be restarted with the updated set."""
    manager = getattr(request.app.state, "camera_manager", None)
    if manager is None:
        return
    camera = db.get(Camera, camera_id)
    if camera is not None and camera.enabled and manager.is_running(camera_id):
        manager.start_camera(camera, db)  # CameraManager.start_camera re-reads zones from DB


@router.get("", response_model=list[ZoneRead])
def list_zones(
    camera_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> list[ZoneRead]:
    query = select(Zone).order_by(Zone.created_at)
    if camera_id is not None:
        query = query.where(Zone.camera_id == camera_id)
    zones = list(db.scalars(query))
    return [ZoneRead.from_orm_zone(z) for z in zones]


@router.post("", response_model=ZoneRead, status_code=status.HTTP_201_CREATED)
def create_zone(
    payload: ZoneCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> ZoneRead:
    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    zone = Zone(
        camera_id=payload.camera_id,
        name=payload.name,
        polygon_json=json.dumps(payload.polygon),
        dwell_time_seconds=payload.dwell_time_seconds,
        cooldown_seconds=payload.cooldown_seconds,
        severity=payload.severity,
        enabled=True,
    )
    db.add(zone)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="zone_created",
            resource_type="zone",
            resource_id=str(zone.id),
            detail=f"camera_id={payload.camera_id} name={payload.name}",
        )
    )
    db.commit()
    db.refresh(zone)

    _reload_camera_zones(request, payload.camera_id, db)
    return ZoneRead.from_orm_zone(zone)


@router.get("/{zone_id}", response_model=ZoneRead)
def get_zone(
    zone_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> ZoneRead:
    return ZoneRead.from_orm_zone(_get_zone_or_404(db, zone_id))


@router.patch("/{zone_id}", response_model=ZoneRead)
def update_zone(
    zone_id: uuid.UUID,
    payload: ZoneUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> ZoneRead:
    zone = _get_zone_or_404(db, zone_id)
    changes = payload.model_dump(exclude_unset=True)
    if "polygon" in changes:
        zone.polygon_json = json.dumps(changes.pop("polygon"))
    for field, value in changes.items():
        setattr(zone, field, value)

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="zone_updated",
            resource_type="zone",
            resource_id=str(zone.id),
            detail=str(changes),
        )
    )
    db.commit()
    db.refresh(zone)

    _reload_camera_zones(request, zone.camera_id, db)
    return ZoneRead.from_orm_zone(zone)


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    zone_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> None:
    zone = _get_zone_or_404(db, zone_id)
    camera_id = zone.camera_id
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="zone_deleted",
            resource_type="zone",
            resource_id=str(zone.id),
            detail=f"name={zone.name}",
        )
    )
    db.delete(zone)
    db.commit()

    _reload_camera_zones(request, camera_id, db)
