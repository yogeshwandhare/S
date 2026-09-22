from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import is_rate_limited, record_attempt, reset
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import BootstrapAdminRequest, LoginRequest, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _set_auth_cookies(response: Response, user_id: str) -> None:
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    secure = settings.ENVIRONMENT == "production"
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        path="/api/auth/refresh",
    )


@router.post("/bootstrap-admin", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def bootstrap_admin(payload: BootstrapAdminRequest, db: Session = Depends(get_db)) -> User:
    """Development-only endpoint to create the first admin account.

    Disabled once any user already exists, and refuses entirely when
    ALLOW_DEV_BOOTSTRAP=false (the documented production posture -- see
    docs/PRODUCTION_SETUP.md for the `scripts/create_admin.py` CLI flow
    that operators should use instead).
    """
    if not settings.ALLOW_DEV_BOOTSTRAP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev bootstrap is disabled. Use scripts/create_admin.py in production.",
        )
    existing = db.scalar(select(User).limit(1))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An admin/user already exists. Bootstrap only works on an empty database.",
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="bootstrap_admin",
            resource_type="user",
            resource_id=str(user.id),
            detail="First admin account created via dev bootstrap endpoint.",
        )
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{payload.email.lower()}"

    if is_rate_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait before trying again.",
        )

    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        record_attempt(rate_key)
        db.add(
            AuditLog(
                actor_user_id=user.id if user else None,
                action="login_failed",
                resource_type="user",
                resource_id=str(user.id) if user else None,
                ip_address=client_ip,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    reset(rate_key)
    _set_auth_cookies(response, str(user.id))
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="login_success",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=client_ip,
        )
    )
    db.commit()
    return user


@router.post("/refresh", response_model=UserRead)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (ValueError, KeyError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    _set_auth_cookies(response, str(user.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth/refresh")


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
