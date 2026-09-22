from __future__ import annotations

import os
import uuid

os.environ.setdefault("DATABASE_URL", f"sqlite:///./test_{uuid.uuid4().hex}.db")
os.environ.setdefault("ALLOW_DEV_BOOTSTRAP", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core import rate_limit
from app.core.database import Base, get_db
from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Login-attempt rate limiting is process-global by design (see
    app/core/rate_limit.py). Reset it between tests so one test's failed
    logins don't bleed into the next test's assertions."""
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


@pytest.fixture()
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(client):
    client.post(
        "/api/auth/bootstrap-admin",
        json={
            "email": "admin@smartvision-demo.com",
            "full_name": "Site Admin",
            "password": "ChangeMeNow123!",
        },
    )
    client.post(
        "/api/auth/login",
        json={"email": "admin@smartvision-demo.com", "password": "ChangeMeNow123!"},
    )
    return client
