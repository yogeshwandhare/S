"""Owns the live `CameraWorker` instances -- one per enabled camera.

A single shared `Detector` instance is loaded once (if the registry has one
enabled + available) and handed to every camera worker, since loading a
model per-camera would be wasteful and, for a CPU host with several
cameras, could exhaust memory.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from vision_worker.detectors.base import Detector
from vision_worker.pipeline.source import FrameSource, FrameSourceConfig, SourceType
from vision_worker.pipeline.worker import CameraHealth, CameraWorker
from vision_worker.rules.abandoned_object import AbandonedObjectRule
from vision_worker.rules.aggressive_motion import AggressiveMotionRule
from vision_worker.rules.intrusion import ZoneConfig, ZoneIntrusionRule
from vision_worker.rules.weapon_confirmation import WeaponConfirmationRule

from app.core.config import get_settings
from app.models.camera import Camera, Zone
from app.models.enums import CameraSourceType

logger = logging.getLogger(__name__)
settings = get_settings()

_SOURCE_TYPE_MAP = {
    CameraSourceType.RTSP: SourceType.RTSP,
    CameraSourceType.FILE: SourceType.FILE,
    CameraSourceType.USB: SourceType.USB,
}

_SAMPLE_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "sample_data")
)


def _load_zone_rules(db: Session, camera_id: uuid.UUID) -> list[ZoneIntrusionRule]:
    zones = list(
        db.scalars(select(Zone).where(Zone.camera_id == camera_id).where(Zone.enabled.is_(True)))
    )
    rules = []
    for zone in zones:
        config = ZoneConfig(
            zone_id=str(zone.id),
            name=zone.name,
            normalized_polygon=[tuple(p) for p in json.loads(zone.polygon_json)],
            dwell_time_seconds=zone.dwell_time_seconds,
            cooldown_seconds=zone.cooldown_seconds,
            severity=zone.severity,
            enabled=zone.enabled,
        )
        rules.append(ZoneIntrusionRule(config))
    return rules


class CameraManager:
    def __init__(self) -> None:
        self._workers: dict[str, CameraWorker] = {}
        self._detector: Detector | None = None
        self._weapon_detector: Detector | None = None
        self._on_rule_triggered: Callable[..., None] | None = None

    def set_detector(self, detector: Detector | None) -> None:
        """Swap the shared detector used by all *newly started* workers.
        Already-running workers keep whatever detector they started with
        until they're restarted -- avoids tearing down every camera stream
        just because the model registry changed."""
        self._detector = detector

    def set_weapon_detector(self, detector: Detector | None) -> None:
        """Same idea as `set_detector`, for the separate weapon-detection
        pass. None (the common case, since no weapon checkpoint ships
        enabled by default) means weapon detection is simply skipped."""
        self._weapon_detector = detector

    def set_incident_callback(self, callback: Callable[..., None] | None) -> None:
        """Wires up what happens when a rule fires -- normally
        `app.services.incident_service.handle_rule_trigger`, which persists
        an Incident row. Kept as an injected callback (rather than importing
        the incident service directly here) so this module has no
        dependency on the incident schema/DB models beyond zones."""
        self._on_rule_triggered = callback

    def start_camera(self, camera: Camera, db: Session) -> None:
        """(Re)starts the worker for this camera, reading its current zones
        from the database. Call this again whenever a camera's zones or
        settings change -- it always tears down any existing worker first,
        so the new one starts with fresh state."""
        camera_id = str(camera.id)
        if camera_id in self._workers:
            self.stop_camera(camera_id)

        uri = camera.source_uri
        if camera.source_type == CameraSourceType.FILE:
            uri = os.path.normpath(os.path.join(_SAMPLE_DATA_DIR, uri))

        source = FrameSource(
            FrameSourceConfig(
                source_type=_SOURCE_TYPE_MAP[camera.source_type],
                uri=uri,
            )
        )
        worker = CameraWorker(
            camera_id=camera_id,
            source=source,
            detector=self._detector,
            inference_fps=camera.inference_fps,
            zone_rules=_load_zone_rules(db, camera.id),
            abandoned_object_rule=AbandonedObjectRule(),
            aggressive_motion_rule=AggressiveMotionRule(),
            weapon_detector=self._weapon_detector,
            weapon_confirmation_rule=(
                WeaponConfirmationRule() if self._weapon_detector is not None else None
            ),
            on_rule_triggered=self._on_rule_triggered,
        )
        worker.start()
        self._workers[camera_id] = worker
        logger.info("Started camera worker for %s (%s)", camera.name, camera_id)

    def stop_camera(self, camera_id: str) -> None:
        worker = self._workers.pop(camera_id, None)
        if worker is not None:
            worker.stop()
            logger.info("Stopped camera worker for %s", camera_id)

    def stop_all(self) -> None:
        for camera_id in list(self._workers.keys()):
            self.stop_camera(camera_id)

    def get_worker(self, camera_id: uuid.UUID | str) -> CameraWorker | None:
        return self._workers.get(str(camera_id))

    def get_health(self, camera_id: uuid.UUID | str) -> CameraHealth | None:
        worker = self.get_worker(camera_id)
        return worker.get_health() if worker else None

    def is_running(self, camera_id: uuid.UUID | str) -> bool:
        return str(camera_id) in self._workers
