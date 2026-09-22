from __future__ import annotations

import uuid
from datetime import UTC, datetime


def _create_camera(admin_client) -> str:
    resp = admin_client.post(
        "/api/cameras",
        json={"name": "Lobby", "source_type": "file", "source_uri": "test.mp4"},
    )
    return resp.json()["id"]


def _make_incident_directly(db_engine, camera_id: str):
    """Incidents are normally created only by the rule engine's callback
    (see test_incident_service.py for that path); for pure API-layer tests
    it's simpler and more direct to insert one via the ORM."""
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
    from app.models.incident import Incident

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = Incident(
            camera_id=uuid.UUID(camera_id),
            category=IncidentCategory.INTRUSION,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.NEW,
            evidence_json='{"dwell_seconds": 3.2, "zone_name": "Loading Dock"}',
            track_ids_json="[7]",
            dedup_key="intrusion:test:zone-1:7",
            alert_delivery_status="pending",
            event_started_at=datetime.now(UTC),
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return str(incident.id)


def test_list_incidents_empty_by_default(admin_client):
    resp = admin_client.get("/api/incidents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_and_get_incident(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    list_resp = admin_client.get("/api/incidents")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert len(body) == 1
    assert body[0]["category"] == "intrusion"
    assert body[0]["evidence"]["zone_name"] == "Loading Dock"
    assert body[0]["track_ids"] == [7]

    get_resp = admin_client.get(f"/api/incidents/{incident_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == incident_id


def test_filter_incidents_by_status(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    _make_incident_directly(db_engine, camera_id)

    new_resp = admin_client.get("/api/incidents?status=new")
    assert len(new_resp.json()) == 1

    resolved_resp = admin_client.get("/api/incidents?status=resolved")
    assert len(resolved_resp.json()) == 0


def test_viewer_cannot_review_incident(client, db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        db.add(
            User(
                email="viewer@smartvision-demo.com",
                full_name="Viewer",
                hashed_password=hash_password("ChangeMeNow123!"),
                role=UserRole.VIEWER,
                is_active=True,
            )
        )
        db.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "viewer@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    assert login.status_code == 200

    camera_resp = client.get("/api/cameras")  # viewer can at least list (no cameras exist)
    assert camera_resp.status_code == 200

    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.patch(f"/api/incidents/{fake_id}", json={"status": "acknowledged"})
    assert resp.status_code == 403


def test_operator_can_acknowledge_incident(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    resp = admin_client.patch(f"/api/incidents/{incident_id}", json={"status": "acknowledged"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None


def test_resolving_incident_sets_resolved_at(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    resp = admin_client.patch(
        f"/api/incidents/{incident_id}",
        json={"status": "resolved", "review_notes": "Confirmed false alarm cleanup crew"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["review_notes"] == "Confirmed false alarm cleanup crew"


def test_false_positive_marking(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    resp = admin_client.patch(
        f"/api/incidents/{incident_id}",
        json={"status": "false_positive", "human_confirmed": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "false_positive"
    assert body["human_confirmed"] is False
    assert body["resolved_at"] is not None


def test_incident_review_creates_timeline_entry(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    admin_client.patch(f"/api/incidents/{incident_id}", json={"status": "acknowledged"})

    timeline_resp = admin_client.get(f"/api/incidents/{incident_id}/timeline")
    assert timeline_resp.status_code == 200
    events = timeline_resp.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "reviewed"


def test_incident_snapshot_404s_when_none_saved(admin_client, db_engine):
    camera_id = _create_camera(admin_client)
    incident_id = _make_incident_directly(db_engine, camera_id)

    resp = admin_client.get(f"/api/incidents/{incident_id}/snapshot")
    assert resp.status_code == 404


def test_get_nonexistent_incident_404s(admin_client):
    resp = admin_client.get("/api/incidents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
