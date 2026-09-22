from __future__ import annotations


def test_list_sample_videos_requires_admin(client, db_engine):
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
    resp = client.get("/api/demo/sample-videos")
    assert resp.status_code == 403


def test_list_sample_videos_returns_real_files(admin_client):
    resp = admin_client.get("/api/demo/sample-videos")
    assert resp.status_code == 200
    filenames = [v["filename"] for v in resp.json()]
    assert "synthetic_pipeline_test.mp4" in filenames


def test_launch_demo_creates_labeled_camera(admin_client):
    resp = admin_client.post(
        "/api/demo",
        json={"filename": "synthetic_pipeline_test.mp4", "camera_name": "My Demo"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Demo"
    assert body["source_type"] == "file"


def test_launch_demo_with_nonexistent_file_404s(admin_client):
    resp = admin_client.post(
        "/api/demo",
        json={"filename": "does-not-exist.mp4", "camera_name": "Bad Demo"},
    )
    assert resp.status_code == 404


def test_launch_demo_rejects_non_mp4_path_traversal(admin_client):
    resp = admin_client.post(
        "/api/demo",
        json={"filename": "../../etc/passwd", "camera_name": "Bad"},
    )
    assert resp.status_code == 404


def test_launch_demo_rejects_traversal_even_with_mp4_suffix(admin_client):
    """A filename that merely ends in .mp4 must still be rejected if it
    contains any path-traversal characters -- checking only the file
    extension would let a crafted path like '../../evil.mp4' through if
    such a file happened to exist outside sample_data/."""
    resp = admin_client.post(
        "/api/demo",
        json={"filename": "../../etc/evil.mp4", "camera_name": "Bad"},
    )
    assert resp.status_code == 404

    resp2 = admin_client.post(
        "/api/demo",
        json={"filename": "subdir/evil.mp4", "camera_name": "Bad"},
    )
    assert resp2.status_code == 404


def test_launch_demo_recorded_in_audit_log(admin_client):
    admin_client.post(
        "/api/demo",
        json={"filename": "synthetic_pipeline_test.mp4", "camera_name": "Audited Demo"},
    )
    resp = admin_client.get("/api/audit-logs")
    actions = [entry["action"] for entry in resp.json()]
    assert "demo_camera_launched" in actions
