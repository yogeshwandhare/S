from __future__ import annotations


def _login_as(client, email: str, password: str = "ChangeMeNow123!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_create_camera_requires_admin(client, db_engine):
    """A logged-in viewer must not be able to create a camera."""
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

    _login_as(client, "viewer@smartvision-demo.com")
    resp = client.post(
        "/api/cameras",
        json={
            "name": "Lobby Camera",
            "source_type": "file",
            "source_uri": "test.mp4",
        },
    )
    assert resp.status_code == 403


def test_create_and_list_camera(admin_client):
    resp = admin_client.post(
        "/api/cameras",
        json={
            "name": "Lobby Camera",
            "source_type": "file",
            "source_uri": "test.mp4",
            "inference_fps": 3.0,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Lobby Camera"
    # "test.mp4" isn't a real file, so the worker's capture thread genuinely
    # fails to open it -- whether that's already been detected by the time
    # this response is built is a real race (local file opens fail fast,
    # but not instantaneously), so either "offline" (not yet attempted) or
    # "error" (already failed) is a correct, honest status here. What would
    # be wrong is silently reporting "online".
    assert body["status"] in ("offline", "error")
    assert "source_uri" not in body  # never leak the raw URI/credentials

    list_resp = admin_client.get("/api/cameras")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_camera_rtsp_blocks_link_local_metadata_address(admin_client):
    resp = admin_client.post(
        "/api/cameras",
        json={
            "name": "Suspicious Camera",
            "source_type": "rtsp",
            "source_uri": "rtsp://169.254.169.254/latest/meta-data",
        },
    )
    assert resp.status_code == 422


def test_camera_rtsp_allows_private_lan_address(admin_client):
    resp = admin_client.post(
        "/api/cameras",
        json={
            "name": "LAN Camera",
            "source_type": "rtsp",
            "source_uri": "rtsp://192.168.1.50:554/stream1",
        },
    )
    assert resp.status_code == 201


def test_camera_file_source_rejects_absolute_path_traversal(admin_client):
    resp = admin_client.post(
        "/api/cameras",
        json={
            "name": "Traversal Attempt",
            "source_type": "file",
            "source_uri": "../../etc/passwd",
        },
    )
    assert resp.status_code == 422


def test_camera_usb_source_requires_numeric_index(admin_client):
    resp = admin_client.post(
        "/api/cameras",
        json={"name": "Webcam", "source_type": "usb", "source_uri": "not-a-number"},
    )
    assert resp.status_code == 422


def test_update_camera_disables_it(admin_client):
    create_resp = admin_client.post(
        "/api/cameras",
        json={"name": "Cam A", "source_type": "file", "source_uri": "test.mp4"},
    )
    camera_id = create_resp.json()["id"]

    update_resp = admin_client.patch(f"/api/cameras/{camera_id}", json={"enabled": False})
    assert update_resp.status_code == 200
    assert update_resp.json()["enabled"] is False


def test_delete_camera(admin_client):
    create_resp = admin_client.post(
        "/api/cameras",
        json={"name": "Cam To Delete", "source_type": "file", "source_uri": "test.mp4"},
    )
    camera_id = create_resp.json()["id"]

    delete_resp = admin_client.delete(f"/api/cameras/{camera_id}")
    assert delete_resp.status_code == 204

    get_resp = admin_client.get(f"/api/cameras/{camera_id}")
    assert get_resp.status_code == 404


def test_get_nonexistent_camera_404s(admin_client):
    resp = admin_client.get("/api/cameras/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_camera_health_for_nonrunning_camera_reports_disconnected(admin_client):
    create_resp = admin_client.post(
        "/api/cameras",
        json={"name": "Cam No Worker", "source_type": "file", "source_uri": "test.mp4"},
    )
    camera_id = create_resp.json()["id"]

    # A real camera_manager IS wired up (it's created unconditionally in
    # app.state, even in the "test" ENVIRONMENT -- see app/main.py's
    # lifespan), and creating this camera really does start a worker
    # thread. But "test.mp4" isn't a real file, so that worker can never
    # actually connect -- this is exercising the genuine "source
    # unreachable" path, not a mocked-out one.
    health_resp = admin_client.get(f"/api/cameras/{camera_id}/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["connected"] is False


def test_models_registry_endpoint_returns_list(admin_client):
    resp = admin_client.get("/api/models")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_http_camera_source_and_credentials_remain_private(admin_client, monkeypatch):
    monkeypatch.setattr(admin_client.app.state.camera_manager, "start_camera", lambda *args: None)
    response = admin_client.post("/api/cameras", json={
        "name": "Phone", "source_type": "http",
        "source_uri": "http://user:secret@192.168.1.19:8080/video",
    })
    assert response.status_code == 201
    assert response.json()["source_type"] == "http"
    assert "source_uri" not in response.json()
    assert "secret" not in response.text


def test_http_camera_rejects_other_protocols_and_metadata(admin_client):
    for uri in ["file:///etc/passwd", "rtsp://camera/live", "http://169.254.169.254/video"]:
        response = admin_client.post("/api/cameras", json={
            "name": "Invalid", "source_type": "http", "source_uri": uri,
        })
        assert response.status_code == 422


def test_rtsp_rejects_http_with_actionable_message(admin_client):
    response = admin_client.post("/api/cameras", json={
        "name": "Phone", "source_type": "rtsp", "source_uri": "http://192.168.1.19:8080",
    })
    assert response.status_code == 422
    assert "select HTTP / MJPEG" in response.text


def test_usb_discovery_requires_authentication(client):
    assert client.get("/api/cameras/usb-devices").status_code == 401


def test_usb_discovery_without_bridge(admin_client, monkeypatch):
    monkeypatch.delenv("USB_CAMERA_BRIDGE_URL", raising=False)
    response = admin_client.get("/api/cameras/usb-devices")
    assert response.status_code == 200
    assert response.json() == {"discovery_available": False, "devices": []}


def test_usb_discovery_returns_names_without_private_url(admin_client, monkeypatch):
    import httpx
    monkeypatch.setenv("USB_CAMERA_BRIDGE_URL", "http://host/private-token")
    response = httpx.Response(200, json=[{"index": 1, "name": "External webcam"}],
                              request=httpx.Request("GET", "http://host/private-token/devices"))
    monkeypatch.setattr("app.api.cameras.httpx.get", lambda *a, **kw: response)
    result = admin_client.get("/api/cameras/usb-devices")
    assert result.status_code == 200
    assert result.json()["devices"] == [{"index": 1, "name": "External webcam"}]
    assert "private-token" not in result.text


def test_usb_discovery_failure_is_actionable_and_redacted(admin_client, monkeypatch):
    import httpx
    monkeypatch.setenv("USB_CAMERA_BRIDGE_URL", "http://host/private-token")
    def fail(*args, **kwargs):
        raise httpx.ConnectError("Could not connect to http://host/private-token")
    monkeypatch.setattr("app.api.cameras.httpx.get", fail)
    response = admin_client.get("/api/cameras/usb-devices")
    assert response.status_code == 503
    assert "Start the Windows camera bridge" in response.text
    assert "private-token" not in response.text


def test_change_usb_device_preserves_camera_id(admin_client, db_engine):
    from sqlalchemy.orm import Session
    from app.models.camera import Camera
    import uuid
    created = admin_client.post("/api/cameras", json={
        "name": "External", "source_type": "usb", "source_uri": "0",
    }).json()
    response = admin_client.patch(f"/api/cameras/{created['id']}", json={
        "usb_device_index": 2, "enabled": False,
    })
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    with Session(db_engine) as db:
        assert db.get(Camera, uuid.UUID(created["id"])).source_uri == "2"


def test_change_usb_device_rejects_non_usb_camera(admin_client):
    created = admin_client.post("/api/cameras", json={
        "name": "File", "source_type": "file", "source_uri": "test.mp4",
    }).json()
    response = admin_client.patch(f"/api/cameras/{created['id']}", json={"usb_device_index": 1})
    assert response.status_code == 422
