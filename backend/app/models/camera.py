from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CameraSourceType, CameraStatus
from app.models.mixins import TimestampMixin, UUIDPKMixin
from app.models.types import str_enum


class Camera(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cameras"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[CameraSourceType] = mapped_column(
        str_enum(CameraSourceType, length=20), nullable=False
    )
    # For RTSP: validated URL (credentials should be embedded via env-var
    # substitution, never logged/echoed back to the frontend as plaintext).
    # For FILE: relative path under sample_data/ or an uploaded evidence dir.
    # For USB: device index, e.g. "0".
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[CameraStatus] = mapped_column(
        str_enum(CameraStatus, length=20),
        nullable=False,
        default=CameraStatus.OFFLINE,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    inference_fps: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    target_width: Mapped[int] = mapped_column(Integer, default=960, nullable=False)
    last_health_check_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Zone(UUIDPKMixin, TimestampMixin, Base):
    """A restricted-zone polygon drawn over a specific camera's frame.

    Coordinates are stored normalized (0.0-1.0 relative to frame width/height)
    so the zone remains correct if the camera's resolution changes.
    """

    __tablename__ = "zones"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # List of [x, y] pairs in normalized coordinates, JSON-encoded.
    polygon_json: Mapped[str] = mapped_column(Text, nullable=False)
    dwell_time_seconds: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    cooldown_seconds: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    # Optional JSON-encoded active-schedule spec, e.g. days/hours. Null = always active.
    active_schedule_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
