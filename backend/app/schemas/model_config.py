from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ModelTask


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task: ModelTask
    name: str
    license: str
    is_available: bool
    enabled: bool
    confidence_threshold: float
    notes: str | None
    updated_at: datetime
