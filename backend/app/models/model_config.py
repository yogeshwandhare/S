from __future__ import annotations

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import ModelTask
from app.models.mixins import TimestampMixin, UUIDPKMixin
from app.models.types import str_enum


class ModelConfig(UUIDPKMixin, TimestampMixin, Base):
    """Registry entry for a single AI model checkpoint used by the vision worker.

    This is the source of truth the dashboard's Settings > Models page reads
    from, and what `scripts/download_models.py` / `scripts/validate_models.py`
    populate and check. See docs/MODEL_REGISTRY.md for the full license and
    provenance inventory.
    """

    __tablename__ = "model_configs"

    task: Mapped[ModelTask] = mapped_column(
        str_enum(ModelTask, length=30), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    checkpoint_source: Mapped[str] = mapped_column(String(1024), nullable=False)
    checkpoint_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    license: Mapped[str] = mapped_column(String(120), nullable=False)
    # JSON-encoded list of class names actually supported by the checkpoint.
    supported_classes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    # Whether the checkpoint file is actually present & validated on disk.
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
