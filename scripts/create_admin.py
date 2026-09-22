#!/usr/bin/env python3
"""
Create an admin user directly against the configured database.

This is the documented production alternative to the dev-only
POST /api/auth/bootstrap-admin endpoint (which refuses to run at all when
ALLOW_DEV_BOOTSTRAP=false). Run it once, interactively, on the machine or
container that can reach the database:

    # Inside the backend container:
    docker compose exec backend python scripts/create_admin.py

    # Or from a local dev checkout with DATABASE_URL exported:
    cd backend && python ../scripts/create_admin.py
"""

from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def main() -> int:
    print("SmartVision — create an admin user\n")

    email = input("Email: ").strip().lower()
    if not EMAIL_RE.match(email):
        print("That doesn't look like a valid email address.", file=sys.stderr)
        return 1

    full_name = input("Full name: ").strip()
    if not full_name:
        print("Full name is required.", file=sys.stderr)
        return 1

    password = getpass.getpass("Password (min 10 characters): ")
    if len(password) < 10:
        print("Password must be at least 10 characters.", file=sys.stderr)
        return 1
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            print(f"A user with email {email} already exists.", file=sys.stderr)
            return 1

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()

    print(f"\nCreated admin user {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
