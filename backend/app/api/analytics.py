from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any_role
from app.models.camera import Camera
from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
from app.models.incident import Incident
from app.models.user import User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def get_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> dict[str, Any]:
    """Every number here comes from an actual query against the incidents
    table for the requested window -- there is no synthetic/example data
    path. An empty deployment correctly returns all zeros."""
    since = datetime.now(UTC) - timedelta(days=days)

    total = db.scalar(select(func.count(Incident.id)).where(Incident.created_at >= since)) or 0

    by_category: dict[IncidentCategory, int] = dict(
        db.execute(
            select(Incident.category, func.count(Incident.id))
            .where(Incident.created_at >= since)
            .group_by(Incident.category)
        )
        .tuples()
        .all()
    )
    by_severity: dict[IncidentSeverity, int] = dict(
        db.execute(
            select(Incident.severity, func.count(Incident.id))
            .where(Incident.created_at >= since)
            .group_by(Incident.severity)
        )
        .tuples()
        .all()
    )
    by_status: dict[IncidentStatus, int] = dict(
        db.execute(
            select(Incident.status, func.count(Incident.id))
            .where(Incident.created_at >= since)
            .group_by(Incident.status)
        )
        .tuples()
        .all()
    )
    by_camera_rows = (
        db.execute(
            select(Camera.name, func.count(Incident.id))
            .join(Incident, Incident.camera_id == Camera.id)
            .where(Incident.created_at >= since)
            .group_by(Camera.name)
        )
        .tuples()
        .all()
    )

    daily_rows: dict[Any, int] = dict(
        db.execute(
            select(func.date(Incident.created_at), func.count(Incident.id))
            .where(Incident.created_at >= since)
            .group_by(func.date(Incident.created_at))
        )
        .tuples()
        .all()
    )
    trend = []
    for i in range(days):
        day = (since + timedelta(days=i)).date()
        count = daily_rows.get(day, 0) or daily_rows.get(str(day), 0)
        trend.append({"date": day.isoformat(), "count": count})

    acknowledged = list(
        db.scalars(
            select(Incident)
            .where(Incident.created_at >= since)
            .where(Incident.acknowledged_at.is_not(None))
        )
    )
    if acknowledged:
        total_seconds = 0.0
        for incident in acknowledged:
            assert incident.acknowledged_at is not None  # guaranteed by the query filter above
            total_seconds += (incident.acknowledged_at - incident.created_at).total_seconds()
        avg_response_seconds: float | None = total_seconds / len(acknowledged)
    else:
        avg_response_seconds = None

    resolved_count = by_status.get(IncidentStatus.RESOLVED, 0)
    false_positive_count = by_status.get(IncidentStatus.FALSE_POSITIVE, 0)

    return {
        "window_days": days,
        "total_incidents": total,
        "by_category": {k.value: v for k, v in by_category.items()},
        "by_severity": {k.value: v for k, v in by_severity.items()},
        "by_status": {k.value: v for k, v in by_status.items()},
        "by_camera": dict(by_camera_rows),
        "daily_trend": trend,
        "avg_response_time_seconds": avg_response_seconds,
        "resolved_count": resolved_count,
        "false_positive_count": false_positive_count,
    }
