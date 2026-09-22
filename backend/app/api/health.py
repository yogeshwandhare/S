from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/api", tags=["health"])

_started_at = time.monotonic()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db_ok = True
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health probe
        db_ok = False
        db_error = str(exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "uptime_seconds": round(time.monotonic() - _started_at, 1),
        "database": {"connected": db_ok, "error": db_error},
    }
