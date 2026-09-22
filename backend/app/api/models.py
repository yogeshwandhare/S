from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any_role
from app.models.model_config import ModelConfig
from app.models.user import User
from app.schemas.model_config import ModelConfigRead

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelConfigRead])
def list_models(
    db: Session = Depends(get_db), _user: User = Depends(require_any_role)
) -> list[ModelConfig]:
    """Read-only view of the model registry (see docs/MODEL_REGISTRY.md).
    Enabling/disabling a model is a deliberate operator action performed
    via `scripts/download_models.py`, not an HTTP toggle -- see that
    script's docstring for why, particularly for the AGPL-3.0 YOLO
    adapter."""
    return list(db.scalars(select(ModelConfig).order_by(ModelConfig.task, ModelConfig.name)))
