"""Turns a `vision_worker.rules.events.RuleTriggerEvent` into a persisted
`Incident` row plus a saved evidence snapshot.

This is the one place a rule trigger becomes a real, stored, human-
reviewable record. Runs on the camera worker's inference thread (via the
`on_rule_triggered` callback wired up in `CameraManager`), so it opens its
own short-lived DB session rather than reusing a request-scoped one.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
from app.models.incident import Incident, IncidentEvent

logger = logging.getLogger(__name__)
settings = get_settings()

#: If an incident with the same dedup_key was already created within this
#: window, skip creating another one. The rule engine's own per-track
#: cooldown (tens of seconds to minutes) is the primary defense against
#: repeat alerts; this is a narrow safety net for the edge case where a
#: worker restart re-creates rule objects (resetting their in-memory
#: cooldown state) in quick succession.
_DEDUP_SAFETY_WINDOW = timedelta(seconds=30)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]")

_CATEGORY_MAP = {
    "intrusion": IncidentCategory.INTRUSION,
    "abandoned_object": IncidentCategory.ABANDONED_OBJECT,
    "aggressive_motion": IncidentCategory.AGGRESSIVE_MOTION,
    "weapon": IncidentCategory.WEAPON,
}


def _safe_filename(value: str) -> str:
    return _SAFE_FILENAME_RE.sub("_", value)


def _save_snapshot(incident_id: uuid.UUID, snapshot: bytes) -> str:
    evidence_dir = os.path.join(settings.EVIDENCE_STORAGE_DIR, "snapshots")
    os.makedirs(evidence_dir, exist_ok=True)
    filename = _safe_filename(f"{incident_id}.jpg")
    path = os.path.join(evidence_dir, filename)
    with open(path, "wb") as f:
        f.write(snapshot)
    return path


def handle_rule_trigger(event, snapshot: bytes) -> None:
    """The callback CameraManager wires up as CameraWorker's
    on_rule_triggered. `event` is a vision_worker.rules.events.RuleTriggerEvent
    -- typed loosely here (not imported) to avoid a hard import-ordering
    dependency; the fields used are that class's documented contract."""
    category = _CATEGORY_MAP.get(event.category)
    if category is None:
        logger.error("Unknown rule trigger category: %s", event.category)
        return

    try:
        severity = IncidentSeverity(event.severity)
    except ValueError:
        severity = IncidentSeverity.MEDIUM

    try:
        camera_uuid = uuid.UUID(event.camera_id)
    except ValueError:
        logger.error("Rule trigger had non-UUID camera_id: %s", event.camera_id)
        return

    with SessionLocal() as db:
        recent_cutoff = datetime.now(UTC) - _DEDUP_SAFETY_WINDOW
        existing = db.scalar(
            select(Incident)
            .where(Incident.dedup_key == event.dedup_key)
            .where(Incident.created_at >= recent_cutoff)
            .limit(1)
        )
        if existing is not None:
            logger.debug("Skipping duplicate incident for dedup_key=%s", event.dedup_key)
            return

        evidence = dict(event.evidence)
        if event.zone_name:
            evidence["zone_name"] = event.zone_name

        incident = Incident(
            camera_id=camera_uuid,
            category=category,
            severity=severity,
            status=IncidentStatus.NEW,
            model_name=None,
            ai_confidence=None,
            evidence_json=json.dumps(evidence),
            track_ids_json=json.dumps(event.track_ids),
            dedup_key=event.dedup_key,
            alert_delivery_status="pending",
            event_started_at=event.occurred_at,
        )
        db.add(incident)
        db.flush()

        try:
            incident.snapshot_path = _save_snapshot(incident.id, snapshot)
        except OSError:
            logger.exception("Failed to save evidence snapshot for incident %s", incident.id)

        db.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_user_id=None,
                event_type="created",
                detail=f"Auto-created by rule engine ({event.category})",
            )
        )

        try:
            from app.services.notification_service import create_notifications_for_incident

            create_notifications_for_incident(db, incident)
        except Exception:
            # Notification creation must never prevent the incident itself
            # from being saved.
            logger.exception("Failed to create notifications for incident %s", incident.id)

        db.commit()
        logger.info(
            "Created incident %s (%s, severity=%s, camera=%s)",
            incident.id,
            category.value,
            severity.value,
            camera_uuid,
        )
