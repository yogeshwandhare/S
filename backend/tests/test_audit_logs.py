from __future__ import annotations


def test_audit_logs_requires_admin(client, db_engine):
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

    client.post(
        "/api/auth/login",
        json={"email": "viewer@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    resp = client.get("/api/audit-logs")
    assert resp.status_code == 403


def test_bootstrap_and_login_are_recorded_in_audit_log(admin_client):
    resp = admin_client.get("/api/audit-logs")
    assert resp.status_code == 200
    actions = [entry["action"] for entry in resp.json()]
    assert "bootstrap_admin" in actions
    assert "login_success" in actions


def test_camera_creation_recorded_in_audit_log(admin_client):
    admin_client.post(
        "/api/cameras", json={"name": "Cam", "source_type": "file", "source_uri": "test.mp4"}
    )
    resp = admin_client.get("/api/audit-logs")
    actions = [entry["action"] for entry in resp.json()]
    assert "camera_created" in actions


def test_user_management_recorded_in_audit_log(admin_client):
    admin_client.post(
        "/api/users",
        json={
            "email": "newuser@smartvision-demo.com",
            "full_name": "New User",
            "password": "ChangeMeNow123!",
            "role": "viewer",
        },
    )
    resp = admin_client.get("/api/audit-logs")
    actions = [entry["action"] for entry in resp.json()]
    assert "user_created" in actions


def test_audit_logs_ordered_most_recent_first(admin_client):
    admin_client.post(
        "/api/cameras", json={"name": "Cam A", "source_type": "file", "source_uri": "a.mp4"}
    )
    admin_client.post(
        "/api/cameras", json={"name": "Cam B", "source_type": "file", "source_uri": "b.mp4"}
    )
    resp = admin_client.get("/api/audit-logs")
    timestamps = [entry["created_at"] for entry in resp.json()]
    assert timestamps == sorted(timestamps, reverse=True)
