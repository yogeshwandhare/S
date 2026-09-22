from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import CameraSourceType, CameraStatus

# Private/loopback/link-local ranges a browser-supplied RTSP host must not
# resolve into, unless the operator explicitly allows internal cameras via
# ALLOW_PRIVATE_CAMERA_NETWORKS (see Settings -- added when this becomes
# configurable). For now this is a hardcoded allowlist-by-exception: RFC
# 1918 / loopback ranges ARE the expected place real IP cameras live on a
# LAN, so we allow private-network RTSP hosts but still block the more
# dangerous ranges (link-local metadata endpoints, multicast, reserved).
_BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_camera_source_uri(source_type: CameraSourceType, uri: str) -> str:
    if source_type == CameraSourceType.USB:
        if not uri.strip().isdigit():
            raise ValueError("USB source must be a device index, e.g. '0'")
        return uri.strip()

    if source_type == CameraSourceType.FILE:
        if ".." in uri or uri.startswith("/"):
            # Files are resolved relative to the server's configured sample
            # data / upload directory only -- never an arbitrary absolute
            # host path from client input.
            raise ValueError("File source must be a relative filename, not an absolute path")
        return uri

    if source_type == CameraSourceType.RTSP:
        parsed = urlparse(uri)
        if parsed.scheme not in ("rtsp", "rtsps"):
            raise ValueError("RTSP source must use the rtsp:// or rtsps:// scheme")
        if not parsed.hostname:
            raise ValueError("RTSP source must include a host")
        try:
            ip = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            ip = None  # hostname, not a literal IP -- resolved at connect time
        if ip is not None:
            for network in _BLOCKED_IP_NETWORKS:
                if ip in network:
                    raise ValueError(f"RTSP host {parsed.hostname} is in a blocked network range")
        return uri

    raise ValueError(f"Unsupported source type: {source_type}")


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: CameraSourceType
    source_uri: str = Field(max_length=1024)
    inference_fps: float = Field(default=5.0, ge=0.5, le=30.0)
    target_width: int = Field(default=960, ge=160, le=3840)
    notes: str | None = None

    @field_validator("source_uri")
    @classmethod
    def _validate_uri(cls, v: str, info) -> str:
        source_type = info.data.get("source_type")
        if source_type is None:
            return v
        return validate_camera_source_uri(source_type, v)


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    inference_fps: float | None = Field(default=None, ge=0.5, le=30.0)
    target_width: int | None = Field(default=None, ge=160, le=3840)
    notes: str | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: CameraSourceType
    # source_uri is intentionally omitted from the API response -- it may
    # embed RTSP credentials. Use CameraReadWithSource (admin-only) if the
    # raw URI is genuinely needed.
    status: CameraStatus
    enabled: bool
    inference_fps: float
    target_width: int
    last_error: str | None
    notes: str | None
    created_at: datetime


class CameraHealthRead(BaseModel):
    camera_id: uuid.UUID
    connected: bool
    last_frame_at: datetime | None
    last_error: str | None
    measured_capture_fps: float
    measured_inference_fps: float
    consecutive_reconnect_attempts: int
    active_track_count: int
