"""Shared enumerations for the SmartVision schema.

Kept as plain Python `str` enums (rather than native Postgres ENUM types) so
that adding a new value later is a simple code change plus a cheap
`VARCHAR` migration, not an `ALTER TYPE`.
"""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class CameraStatus(enum.StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    DISABLED = "disabled"


class CameraSourceType(enum.StrEnum):
    RTSP = "rtsp"
    FILE = "file"
    USB = "usb"


class IncidentCategory(enum.StrEnum):
    INTRUSION = "intrusion"
    ABANDONED_OBJECT = "abandoned_object"
    AGGRESSIVE_MOTION = "aggressive_motion"  # heuristic-only, review required
    FIGHT = "fight"  # only used once a validated classifier is enabled
    WEAPON = "weapon"


class IncidentSeverity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(enum.StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class ModelTask(enum.StrEnum):
    OBJECT_DETECTION = "object_detection"
    POSE_ESTIMATION = "pose_estimation"
    ACTION_RECOGNITION = "action_recognition"
    WEAPON_DETECTION = "weapon_detection"


class NotificationChannel(enum.StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED_NOT_CONFIGURED = "skipped_not_configured"
