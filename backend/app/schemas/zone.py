from __future__ import annotations

import json
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ZoneCreate(BaseModel):
    camera_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    # List of [x, y] pairs, normalized to 0.0-1.0 relative to frame size.
    polygon: list[tuple[float, float]] = Field(min_length=3)
    dwell_time_seconds: float = Field(default=1.0, ge=0.0, le=300.0)
    cooldown_seconds: float = Field(default=60.0, ge=0.0, le=3600.0)
    severity: str = Field(default="medium")

    @field_validator("polygon")
    @classmethod
    def _validate_normalized(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        for x, y in v:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("Polygon coordinates must be normalized between 0.0 and 1.0")
        return v

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {sorted(allowed)}")
        return v


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    polygon: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    dwell_time_seconds: float | None = Field(default=None, ge=0.0, le=300.0)
    cooldown_seconds: float | None = Field(default=None, ge=0.0, le=3600.0)
    severity: str | None = None
    enabled: bool | None = None


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    polygon: list[tuple[float, float]]
    dwell_time_seconds: float
    cooldown_seconds: float
    severity: str
    enabled: bool
    created_at: datetime

    @classmethod
    def from_orm_zone(cls, zone) -> ZoneRead:
        return cls(
            id=zone.id,
            camera_id=zone.camera_id,
            name=zone.name,
            polygon=json.loads(zone.polygon_json),
            dwell_time_seconds=zone.dwell_time_seconds,
            cooldown_seconds=zone.cooldown_seconds,
            severity=zone.severity,
            enabled=zone.enabled,
            created_at=zone.created_at,
        )
