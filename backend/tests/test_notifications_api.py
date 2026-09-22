from __future__ import annotations


def test_list_notifications_empty_by_default(admin_client):
    resp = admin_client.get("/api/notifications")
    assert resp.status_code == 200
    assert resp.json() == []


def test_notifications_require_auth(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 401


def test_mark_read_on_nonexistent_notification_404s(admin_client):
    resp = admin_client.post("/api/notifications/00000000-0000-0000-0000-000000000000/read")
    assert resp.status_code == 404


def test_list_and_mark_read_own_notification(admin_client, db_engine):
    from datetime import UTC, datetime

    from sqlalchemy.orm import sessionmaker

    from app.models.camera import Camera
    from app.models.enums import (
        CameraSourceType,
        IncidentCategory,
        IncidentSeverity,
        IncidentStatus,
        NotificationChannel,
        NotificationStatus,
    )
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.models.user import User

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        admin = db.query(User).filter_by(email="admin@smartvision-demo.com").one()
        camera = Camera(name="Cam", source_type=CameraSourceType.FILE, source_uri="test.mp4")
        db.add(camera)
        db.flush()
        incident = Incident(
            camera_id=camera.id,
            category=IncidentCategory.INTRUSION,
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.NEW,
            dedup_key="k",
            alert_delivery_status="pending",
            event_started_at=datetime.now(UTC),
        )
        db.add(incident)
        db.flush()
        notification = Notification(
            incident_id=incident.id,
            recipient_user_id=admin.id,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.SENT,
            dedup_key="k:in_app",
        )
        db.add(notification)
        db.commit()
        notification_id = str(notification.id)

    list_resp = admin_client.get("/api/notifications")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["read_at"] is None

    read_resp = admin_client.post(f"/api/notifications/{notification_id}/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["read_at"] is not None

    unread_resp = admin_client.get("/api/notifications?unread_only=true")
    assert unread_resp.json() == []
