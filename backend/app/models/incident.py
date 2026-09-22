from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow
from app.models.types import str_enum


class Incident(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[IncidentCategory] = mapped_column(
        str_enum(IncidentCategory, length=30), nullable=False, index=True
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        str_enum(IncidentSeverity, length=20), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus, length=20),
        nullable=False,
        default=IncidentStatus.NEW,
        index=True,
    )

    # --- AI provenance (never conflated with human confirmation) ---
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # JSON blob: rule evidence, e.g. dwell time, track ids, zone id, motion score.
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    track_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Evidence artifacts ---
    snapshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # --- Human review ---
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_confirmed: Mapped[bool | None] = mapped_column(nullable=True)

    # --- Deduplication / delivery ---
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alert_delivery_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )

    event_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentEvent(UUIDPKMixin, Base):
    """Append-only audit trail entry for an incident (status change, note, etc.)."""

    __tablename__ = "incident_events"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
