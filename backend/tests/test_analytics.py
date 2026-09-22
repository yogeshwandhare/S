from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta


def _make_camera(db_engine, name="Cam") -> str:
    from sqlalchemy.orm import sessionmaker

    from app.models.camera import Camera
    from app.models.enums import CameraSourceType

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        camera = Camera(name=name, source_type=CameraSourceType.FILE, source_uri="test.mp4")
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return str(camera.id)


def _make_incident(
    db_engine,
    camera_id: str,
    category="intrusion",
    severity="high",
    status="new",
    created_at=None,
    acknowledged_at=None,
):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
    from app.models.incident import Incident

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = Incident(
            camera_id=uuid.UUID(camera_id),
            category=IncidentCategory(category),
            severity=IncidentSeverity(severity),
            status=IncidentStatus(status),
            dedup_key=str(uuid.uuid4()),
            alert_delivery_status="pending",
            event_started_at=created_at or datetime.now(UTC),
            acknowledged_at=acknowledged_at,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        if created_at:
            incident.created_at = created_at
            db.commit()
        return incident.id


def test_analytics_summary_empty_returns_zeros(admin_client):
    resp = admin_client.get("/api/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_incidents"] == 0
    assert body["by_category"] == {}
    assert body["resolved_count"] == 0
    assert body["avg_response_time_seconds"] is None
    assert len(body["daily_trend"]) == body["window_days"]


def test_analytics_summary_counts_real_incidents(admin_client, db_engine):
    camera_id = _make_camera(db_engine)
    _make_incident(db_engine, camera_id, category="intrusion", severity="high")
    _make_incident(db_engine, camera_id, category="abandoned_object", severity="medium")
    _make_incident(db_engine, camera_id, category="intrusion", severity="high", status="resolved")

    resp = admin_client.get("/api/analytics/summary")
    body = resp.json()
    assert body["total_incidents"] == 3
    assert body["by_category"]["intrusion"] == 2
    assert body["by_category"]["abandoned_object"] == 1
    assert body["resolved_count"] == 1


def test_analytics_by_camera_breakdown(admin_client, db_engine):
    cam_a = _make_camera(db_engine, "Front Door")
    cam_b = _make_camera(db_engine, "Loading Dock")
    _make_incident(db_engine, cam_a)
    _make_incident(db_engine, cam_a)
    _make_incident(db_engine, cam_b)

    resp = admin_client.get("/api/analytics/summary")
    body = resp.json()
    assert body["by_camera"]["Front Door"] == 2
    assert body["by_camera"]["Loading Dock"] == 1


def test_analytics_response_time_computed_from_real_acknowledgements(admin_client, db_engine):
    camera_id = _make_camera(db_engine)
    # acknowledged_at must be meaningfully after creation for this to be a
    # realistic response time -- created_at is assigned by the DB default
    # at insert time, so backdating "now" risks a spurious negative delta.
    now = datetime.now(UTC) + timedelta(seconds=5)
    _make_incident(db_engine, camera_id, acknowledged_at=now)
    _make_incident(db_engine, camera_id)

    resp = admin_client.get("/api/analytics/summary")
    body = resp.json()
    assert body["avg_response_time_seconds"] is not None
    assert body["avg_response_time_seconds"] >= 0


def test_analytics_respects_time_window(admin_client, db_engine):
    camera_id = _make_camera(db_engine)
    old_date = datetime.now(UTC) - timedelta(days=100)
    _make_incident(db_engine, camera_id, created_at=old_date)

    resp = admin_client.get("/api/analytics/summary?days=30")
    body = resp.json()
    assert body["total_incidents"] == 0


def test_analytics_requires_auth(client):
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 401
