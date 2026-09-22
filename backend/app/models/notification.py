from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.mixins import TimestampMixin, UUIDPKMixin
from app.models.types import str_enum


class Notification(UUIDPKMixin, TimestampMixin, Base):
    """A single outbound notification, delivered by the async worker.

    Uses a database-backed outbox: rows are inserted synchronously when an
    incident is created, and a background worker polls for PENDING rows,
    attempts delivery, and updates status with retry/backoff bookkeeping.
    """

    __tablename__ = "notifications"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        str_enum(NotificationChannel, length=20), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, length=30),
        nullable=False,
        default=NotificationStatus.PENDING,
        index=True,
    )
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # In-app notifications are "delivered" the moment the row exists; this
    # tracks whether the recipient has actually seen it in the UI. Always
    # None for email notifications.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
