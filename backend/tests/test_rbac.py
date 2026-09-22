from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.deps import require_roles
from app.models.enums import UserRole
from app.models.user import User


def _fake_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        email="x@smartvision-demo.com",
        full_name="X",
        hashed_password="irrelevant",
        role=role,
        is_active=True,
    )


def test_require_roles_allows_listed_role():
    checker = require_roles(UserRole.ADMIN, UserRole.OPERATOR)
    result = checker(_fake_user(UserRole.OPERATOR))
    assert result.role == UserRole.OPERATOR


def test_require_roles_rejects_unlisted_role():
    checker = require_roles(UserRole.ADMIN)
    with pytest.raises(HTTPException) as exc_info:
        checker(_fake_user(UserRole.VIEWER))
    assert exc_info.value.status_code == 403


def test_require_roles_viewer_cannot_access_admin_only():
    checker = require_roles(UserRole.ADMIN)
    with pytest.raises(HTTPException) as exc_info:
        checker(_fake_user(UserRole.VIEWER))
    assert exc_info.value.status_code == 403


def test_require_roles_admin_allowed_everywhere_explicitly_listed():
    checker = require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)
    result = checker(_fake_user(UserRole.ADMIN))
    assert result.role == UserRole.ADMIN
