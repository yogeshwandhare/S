from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class _FakeRuleTriggerEvent:
    """Mirrors vision_worker.rules.events.RuleTriggerEvent's field shape --
    incident_service deliberately doesn't import that class (see its
    module docstring), so this fake stands in for it in tests too."""

    category: str
    camera_id: str
    track_ids: list[int]
    severity: str
    occurred_at: datetime
    zone_id: str | None = None
    zone_name: str | None = None
    evidence: dict = field(default_factory=dict)
    dedup_key: str = "test-dedup-key"


def _make_camera(db_engine) -> str:
    from sqlalchemy.orm import sessionmaker

    from app.models.camera import Camera
    from app.models.enums import CameraSourceType

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        camera = Camera(
            name="Test Cam",
            source_type=CameraSourceType.FILE,
            source_uri="test.mp4",
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return str(camera.id)


def test_handle_rule_trigger_creates_incident(db_engine, monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident
    from app.services import incident_service

    test_session_local = sessionmaker(bind=db_engine)
    monkeypatch.setattr(incident_service, "SessionLocal", test_session_local)
    monkeypatch.setattr(incident_service.settings, "EVIDENCE_STORAGE_DIR", str(tmp_path))

    camera_id = _make_camera(db_engine)
    event = _FakeRuleTriggerEvent(
        category="intrusion",
        camera_id=camera_id,
        track_ids=[3],
        severity="high",
        occurred_at=datetime.now(UTC),
        zone_id="zone-1",
        zone_name="Loading Dock",
        evidence={"dwell_seconds": 4.2},
        dedup_key="intrusion:cam:zone-1:3",
    )

    incident_service.handle_rule_trigger(event, snapshot=b"\xff\xd8fake-jpeg-bytes")

    with test_session_local() as db:
        incidents = db.query(Incident).all()
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.category.value == "intrusion"
        assert incident.severity.value == "high"
        assert incident.status.value == "new"
        assert incident.dedup_key == "intrusion:cam:zone-1:3"
        assert incident.snapshot_path is not None
        assert os.path.exists(incident.snapshot_path)
        with open(incident.snapshot_path, "rb") as f:
            assert f.read() == b"\xff\xd8fake-jpeg-bytes"


def test_handle_rule_trigger_deduplicates_within_safety_window(db_engine, monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident
    from app.services import incident_service

    test_session_local = sessionmaker(bind=db_engine)
    monkeypatch.setattr(incident_service, "SessionLocal", test_session_local)
    monkeypatch.setattr(incident_service.settings, "EVIDENCE_STORAGE_DIR", str(tmp_path))

    camera_id = _make_camera(db_engine)
    event = _FakeRuleTriggerEvent(
        category="abandoned_object",
        camera_id=camera_id,
        track_ids=[9],
        severity="medium",
        occurred_at=datetime.now(UTC),
        evidence={"stationary_seconds": 61.0},
        dedup_key="abandoned_object:cam:none:9",
    )

    incident_service.handle_rule_trigger(event, snapshot=b"frame-1")
    incident_service.handle_rule_trigger(event, snapshot=b"frame-2")

    with test_session_local() as db:
        incidents = db.query(Incident).filter_by(dedup_key="abandoned_object:cam:none:9").all()
        assert len(incidents) == 1


def test_handle_rule_trigger_ignores_unknown_category(db_engine, monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident
    from app.services import incident_service

    test_session_local = sessionmaker(bind=db_engine)
    monkeypatch.setattr(incident_service, "SessionLocal", test_session_local)
    monkeypatch.setattr(incident_service.settings, "EVIDENCE_STORAGE_DIR", str(tmp_path))

    camera_id = _make_camera(db_engine)
    event = _FakeRuleTriggerEvent(
        category="something_unrecognized",
        camera_id=camera_id,
        track_ids=[1],
        severity="low",
        occurred_at=datetime.now(UTC),
    )

    incident_service.handle_rule_trigger(event, snapshot=b"x")

    with test_session_local() as db:
        assert db.query(Incident).count() == 0


def test_handle_rule_trigger_creates_audit_timeline_entry(db_engine, monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident, IncidentEvent
    from app.services import incident_service

    test_session_local = sessionmaker(bind=db_engine)
    monkeypatch.setattr(incident_service, "SessionLocal", test_session_local)
    monkeypatch.setattr(incident_service.settings, "EVIDENCE_STORAGE_DIR", str(tmp_path))

    camera_id = _make_camera(db_engine)
    event = _FakeRuleTriggerEvent(
        category="intrusion",
        camera_id=camera_id,
        track_ids=[1],
        severity="low",
        occurred_at=datetime.now(UTC),
        dedup_key="unique-key-for-this-test",
    )
    incident_service.handle_rule_trigger(event, snapshot=b"x")

    with test_session_local() as db:
        incident = db.query(Incident).one()
        events = db.query(IncidentEvent).filter_by(incident_id=incident.id).all()
        assert len(events) == 1
        assert events[0].event_type == "created"
