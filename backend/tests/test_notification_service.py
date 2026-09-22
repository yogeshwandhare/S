from __future__ import annotations

from datetime import UTC, datetime


def _make_camera(db_engine) -> str:
    from sqlalchemy.orm import sessionmaker

    from app.models.camera import Camera
    from app.models.enums import CameraSourceType

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        camera = Camera(name="Test Cam", source_type=CameraSourceType.FILE, source_uri="test.mp4")
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return str(camera.id)


def _make_incident(db_engine, camera_id: str, dedup_key: str = "test-dedup"):
    import uuid

    from sqlalchemy.orm import sessionmaker

    from app.models.enums import IncidentCategory, IncidentSeverity, IncidentStatus
    from app.models.incident import Incident

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = Incident(
            camera_id=uuid.UUID(camera_id),
            category=IncidentCategory.INTRUSION,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.NEW,
            dedup_key=dedup_key,
            alert_delivery_status="pending",
            event_started_at=datetime.now(UTC),
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return incident.id


def _make_user(db_engine, email: str, role: str, active: bool = True):
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        user = User(
            email=email,
            full_name=email,
            hashed_password=hash_password("ChangeMeNow123!"),
            role=UserRole(role),
            is_active=active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def test_creates_in_app_notifications_for_admins_and_operators(db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services.notification_service import create_notifications_for_incident

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")
    _make_user(db_engine, "operator@smartvision-demo.com", "operator")
    _make_user(db_engine, "viewer@smartvision-demo.com", "viewer")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        create_notifications_for_incident(db, incident)
        db.commit()

        in_app = db.query(Notification).filter_by(channel=NotificationChannel.IN_APP).all()
        assert len(in_app) == 2  # admin + operator, never the viewer


def test_creates_email_notification_only_for_admins(db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services.notification_service import create_notifications_for_incident

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")
    _make_user(db_engine, "operator@smartvision-demo.com", "operator")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        create_notifications_for_incident(db, incident)
        db.commit()

        emails = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).all()
        assert len(emails) == 1


def test_inactive_users_never_notified(db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services.notification_service import create_notifications_for_incident

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin", active=False)

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        create_notifications_for_incident(db, incident)
        db.commit()
        assert db.query(Notification).count() == 0


def test_process_pending_skips_when_smtp_not_configured(db_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel, NotificationStatus
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services import notification_service

    monkeypatch.setattr(notification_service.settings, "SMTP_HOST", None)

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        notification_service.create_notifications_for_incident(db, incident)
        db.commit()

        processed = notification_service.process_pending_notifications(db)
        assert processed == 1

        email_notification = (
            db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        )
        assert email_notification.status == NotificationStatus.SKIPPED_NOT_CONFIGURED


def test_process_pending_retries_on_failure_with_backoff(db_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel, NotificationStatus
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services import notification_service

    monkeypatch.setattr(notification_service.settings, "SMTP_HOST", "smtp.example.com")

    def _raise(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(notification_service, "_send_email", _raise)

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        notification_service.create_notifications_for_incident(db, incident)
        db.commit()

        notification_service.process_pending_notifications(db)

        notification = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        assert notification.status == NotificationStatus.PENDING  # still retrying, not FAILED yet
        assert notification.attempt_count == 1
        assert notification.next_attempt_at is not None
        assert "connection refused" in notification.error_message


def test_process_pending_marks_failed_after_max_attempts(db_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel, NotificationStatus
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services import notification_service

    monkeypatch.setattr(notification_service.settings, "SMTP_HOST", "smtp.example.com")

    def _raise(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(notification_service, "_send_email", _raise)
    monkeypatch.setattr(notification_service, "_MAX_ATTEMPTS", 2)

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        notification_service.create_notifications_for_incident(db, incident)
        db.commit()

        notification = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        notification.next_attempt_at = None
        db.commit()
        notification_service.process_pending_notifications(db)

        notification = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        notification.next_attempt_at = None
        db.commit()
        notification_service.process_pending_notifications(db)

        notification = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        assert notification.status == NotificationStatus.FAILED
        assert notification.attempt_count == 2


def test_successful_delivery_marks_sent(db_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.models.enums import NotificationChannel, NotificationStatus
    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services import notification_service

    monkeypatch.setattr(notification_service.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notification_service, "_send_email", lambda *a, **kw: None)

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id))
        notification_service.create_notifications_for_incident(db, incident)
        db.commit()

        notification_service.process_pending_notifications(db)

        notification = db.query(Notification).filter_by(channel=NotificationChannel.EMAIL).one()
        assert notification.status == NotificationStatus.SENT


def test_deduplicates_within_window(db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.models.incident import Incident
    from app.models.notification import Notification
    from app.services.notification_service import create_notifications_for_incident

    camera_id = _make_camera(db_engine)
    _make_user(db_engine, "admin@smartvision-demo.com", "admin")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        incident = db.get(Incident, _make_incident(db_engine, camera_id, dedup_key="same-key"))
        create_notifications_for_incident(db, incident)
        create_notifications_for_incident(db, incident)  # simulate a duplicate trigger
        db.commit()

        assert db.query(Notification).count() == 2  # in_app + email, not 4
