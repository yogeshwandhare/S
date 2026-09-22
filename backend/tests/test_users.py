from __future__ import annotations


def test_list_users_requires_admin(client, db_engine):
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
    resp = client.get("/api/users")
    assert resp.status_code == 403


def test_admin_can_list_users(admin_client):
    resp = admin_client.get("/api/users")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_admin_can_create_user(admin_client):
    resp = admin_client.post(
        "/api/users",
        json={
            "email": "operator@smartvision-demo.com",
            "full_name": "Operator One",
            "password": "ChangeMeNow123!",
            "role": "operator",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "operator"
    assert body["is_active"] is True


def test_cannot_create_duplicate_email(admin_client):
    admin_client.post(
        "/api/users",
        json={
            "email": "dup@smartvision-demo.com",
            "full_name": "First",
            "password": "ChangeMeNow123!",
            "role": "viewer",
        },
    )
    resp = admin_client.post(
        "/api/users",
        json={
            "email": "dup@smartvision-demo.com",
            "full_name": "Second",
            "password": "ChangeMeNow123!",
            "role": "viewer",
        },
    )
    assert resp.status_code == 409


def test_deactivate_and_reactivate_user(admin_client):
    create_resp = admin_client.post(
        "/api/users",
        json={
            "email": "toggle@smartvision-demo.com",
            "full_name": "Toggle User",
            "password": "ChangeMeNow123!",
            "role": "operator",
        },
    )
    user_id = create_resp.json()["id"]

    deactivate_resp = admin_client.patch(f"/api/users/{user_id}/deactivate")
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    reactivate_resp = admin_client.patch(f"/api/users/{user_id}/reactivate")
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True


def test_admin_cannot_deactivate_self(admin_client):
    me_resp = admin_client.get("/api/auth/me")
    my_id = me_resp.json()["id"]

    resp = admin_client.patch(f"/api/users/{my_id}/deactivate")
    assert resp.status_code == 400


def test_deactivated_user_cannot_login(admin_client, client):
    create_resp = admin_client.post(
        "/api/users",
        json={
            "email": "will-deactivate@smartvision-demo.com",
            "full_name": "Bye",
            "password": "ChangeMeNow123!",
            "role": "viewer",
        },
    )
    user_id = create_resp.json()["id"]
    admin_client.patch(f"/api/users/{user_id}/deactivate")

    login_resp = client.post(
        "/api/auth/login",
        json={"email": "will-deactivate@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    assert login_resp.status_code == 403
