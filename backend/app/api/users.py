from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _user: User = Depends(require_admin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action="user_created",
            resource_type="user",
            resource_id=str(user.id),
            detail=f"email={payload.email} role={payload.role.value}",
        )
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    user.is_active = False
    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action="user_deactivated",
            resource_type="user",
            resource_id=str(user.id),
            detail=f"email={user.email}",
        )
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/reactivate", response_model=UserRead)
def reactivate_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action="user_reactivated",
            resource_type="user",
            resource_id=str(user.id),
            detail=f"email={user.email}",
        )
    )
    db.commit()
    db.refresh(user)
    return user
