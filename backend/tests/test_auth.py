from __future__ import annotations


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True


def test_bootstrap_admin_creates_user(client):
    resp = client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "admin@smartvision-demo.com",
            "full_name": "Site Admin",
            "password": "ChangeMeNow123!",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "admin"
    assert body["email"] == "admin@smartvision-demo.com"


def test_bootstrap_admin_fails_when_user_exists(admin_client):
    resp = admin_client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "second@smartvision-demo.com",
            "full_name": "Second",
            "password": "ChangeMeNow123!",
        },
    )
    assert resp.status_code == 409


def test_bootstrap_admin_disabled_in_production(client, monkeypatch):
    from app.api import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "ALLOW_DEV_BOOTSTRAP", False)
    resp = client.post(
        "/api/auth/bootstrap-admin",
        json={"email": "x@smartvision-demo.com", "full_name": "X", "password": "ChangeMeNow123!"},
    )
    assert resp.status_code == 403


def test_login_success_sets_cookie(client):
    client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "admin@smartvision-demo.com",
            "full_name": "Site Admin",
            "password": "ChangeMeNow123!",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "admin@smartvision-demo.com",
            "full_name": "Site Admin",
            "password": "ChangeMeNow123!",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@smartvision-demo.com", "password": "totallywrongpassword"},
    )
    assert resp.status_code == 401


def test_login_rate_limited_after_repeated_failures(client):
    client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "admin@smartvision-demo.com",
            "full_name": "Site Admin",
            "password": "ChangeMeNow123!",
        },
    )
    last_status = None
    for _ in range(6):
        resp = client.post(
            "/api/auth/login",
            json={"email": "admin@smartvision-demo.com", "password": "wrong-password"},
        )
        last_status = resp.status_code
    assert last_status == 429


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(admin_client):
    resp = admin_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@smartvision-demo.com"


def test_logout_clears_session(admin_client):
    resp = admin_client.post("/api/auth/logout")
    assert resp.status_code == 204
    resp2 = admin_client.get("/api/auth/me")
    assert resp2.status_code == 401


def test_inactive_user_cannot_login(client, db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        user = User(
            email="disabled@smartvision-demo.com",
            full_name="Disabled",
            hashed_password=hash_password("ChangeMeNow123!"),
            role=UserRole.VIEWER,
            is_active=False,
        )
        db.add(user)
        db.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": "disabled@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    assert resp.status_code == 403
