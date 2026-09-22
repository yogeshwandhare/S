from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.enums import UserRole
from app.models.user import User


def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
    if not access_token:
        raise credentials_error

    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise credentials_error

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_error

    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise credentials_error

    return user


def require_roles(*allowed: UserRole) -> Callable[[User], User]:
    """Dependency factory: raise 403 unless the current user has one of the
    allowed roles. Admin is not implicitly granted every permission here on
    purpose -- callers list exactly which roles may access a route so the
    RBAC matrix stays explicit and auditable."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return _checker


require_admin = require_roles(UserRole.ADMIN)
require_operator_or_admin = require_roles(UserRole.ADMIN, UserRole.OPERATOR)
require_any_role = require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)
