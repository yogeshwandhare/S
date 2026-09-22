"""All ORM models, imported here so Alembic's `target_metadata` sees every
table when autogenerating migrations."""

from app.models.audit_log import AuditLog
from app.models.camera import Camera, Zone
from app.models.incident import Incident, IncidentEvent
from app.models.model_config import ModelConfig
from app.models.notification import Notification
from app.models.user import User

__all__ = [
    "AuditLog",
    "Camera",
    "Zone",
    "Incident",
    "IncidentEvent",
    "ModelConfig",
    "Notification",
    "User",
]
