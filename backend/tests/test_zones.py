from __future__ import annotations


def _create_camera(admin_client) -> str:
    resp = admin_client.post(
        "/api/cameras",
        json={"name": "Lobby", "source_type": "file", "source_uri": "test.mp4"},
    )
    return resp.json()["id"]


def test_create_zone_requires_admin(client, db_engine):
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
    resp = client.post(
        "/api/zones",
        json={
            "camera_id": "00000000-0000-0000-0000-000000000000",
            "name": "Restricted",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        },
    )
    assert resp.status_code == 403


def test_create_zone_for_nonexistent_camera_404s(admin_client):
    resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": "00000000-0000-0000-0000-000000000000",
            "name": "Restricted",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        },
    )
    assert resp.status_code == 404


def test_create_and_list_zone(admin_client):
    camera_id = _create_camera(admin_client)
    resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": camera_id,
            "name": "Loading Dock",
            "polygon": [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
            "dwell_time_seconds": 2.0,
            "severity": "high",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Loading Dock"
    assert body["polygon"] == [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
    assert body["severity"] == "high"

    list_resp = admin_client.get(f"/api/zones?camera_id={camera_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_zone_rejects_out_of_range_coordinates(admin_client):
    camera_id = _create_camera(admin_client)
    resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": camera_id,
            "name": "Bad Zone",
            # 500.0 is a pixel coordinate, not normalized -- must be rejected.
            "polygon": [[0.0, 0.0], [500.0, 0.0], [500.0, 500.0]],
        },
    )
    assert resp.status_code == 422


def test_zone_rejects_fewer_than_three_points(admin_client):
    camera_id = _create_camera(admin_client)
    resp = admin_client.post(
        "/api/zones",
        json={"camera_id": camera_id, "name": "Line", "polygon": [[0.0, 0.0], [1.0, 1.0]]},
    )
    assert resp.status_code == 422


def test_zone_rejects_invalid_severity(admin_client):
    camera_id = _create_camera(admin_client)
    resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": camera_id,
            "name": "Zone",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            "severity": "extremely-bad",
        },
    )
    assert resp.status_code == 422


def test_update_zone_polygon(admin_client):
    camera_id = _create_camera(admin_client)
    create_resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": camera_id,
            "name": "Zone A",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        },
    )
    zone_id = create_resp.json()["id"]

    update_resp = admin_client.patch(
        f"/api/zones/{zone_id}",
        json={"polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["polygon"] == [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def test_delete_zone(admin_client):
    camera_id = _create_camera(admin_client)
    create_resp = admin_client.post(
        "/api/zones",
        json={
            "camera_id": camera_id,
            "name": "Zone To Delete",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        },
    )
    zone_id = create_resp.json()["id"]

    delete_resp = admin_client.delete(f"/api/zones/{zone_id}")
    assert delete_resp.status_code == 204

    get_resp = admin_client.get(f"/api/zones/{zone_id}")
    assert get_resp.status_code == 404
