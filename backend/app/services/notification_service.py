"""Notification outbox: creates notification rows when an incident is
created, and a background worker (see `notification_worker_loop` below,
started from the FastAPI lifespan) periodically attempts delivery.

Design matches the project brief's "database-backed outbox or similarly
simple reliable queue" requirement -- no external queue service, just a
polled table with retry/backoff bookkeeping.

If SMTP isn't configured, email notifications are marked
SKIPPED_NOT_CONFIGURED and everything else keeps working normally -- the
worker never blocks or errors out because of missing SMTP settings.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import NotificationChannel, NotificationStatus, UserRole
from app.models.incident import Incident
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

_RETRY_BACKOFF_MINUTES = [1, 5, 15, 60, 240]
_MAX_ATTEMPTS = 6
WORKER_POLL_INTERVAL_SECONDS = 15
_DEDUP_WINDOW = timedelta(minutes=5)


def create_notifications_for_incident(db: Session, incident: Incident) -> None:
    """Called synchronously right after an incident is persisted (see
    app/services/incident_service.py). Creates in-app notifications for
    every active admin/operator, and an email notification for every
    active admin if SMTP is configured. Viewers are never notified --
    they can't act on an incident anyway."""
    recipients = list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True))
            .where(User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]))
        )
    )

    recent_cutoff = datetime.now(UTC) - _DEDUP_WINDOW

    for user in recipients:
        dedup_key = f"{incident.dedup_key}:in_app:{user.id}"
        if _already_notified(db, dedup_key, recent_cutoff):
            continue
        db.add(
            Notification(
                incident_id=incident.id,
                recipient_user_id=user.id,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                dedup_key=dedup_key,
            )
        )

        if user.role == UserRole.ADMIN:
            email_dedup_key = f"{incident.dedup_key}:email:{user.id}"
            if _already_notified(db, email_dedup_key, recent_cutoff):
                continue
            db.add(
                Notification(
                    incident_id=incident.id,
                    recipient_user_id=user.id,
                    channel=NotificationChannel.EMAIL,
                    status=NotificationStatus.PENDING,
                    dedup_key=email_dedup_key,
                )
            )

    db.flush()


def _already_notified(db: Session, dedup_key: str, since: datetime) -> bool:
    existing = db.scalar(
        select(Notification)
        .where(Notification.dedup_key == dedup_key)
        .where(Notification.created_at >= since)
        .limit(1)
    )
    return existing is not None


def process_pending_notifications(db: Session) -> int:
    """Attempts delivery for every notification that's due (PENDING and
    either never attempted or past its next_attempt_at backoff time).
    Returns the number processed. Safe to call repeatedly -- this is what
    the background worker loop does."""
    now = datetime.now(UTC)
    pending = list(
        db.scalars(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .where(Notification.channel == NotificationChannel.EMAIL)
        )
    )

    processed = 0
    for notification in pending:
        if notification.next_attempt_at is not None and notification.next_attempt_at > now:
            continue
        _attempt_delivery(db, notification)
        processed += 1

    if processed:
        db.commit()
    return processed


def _attempt_delivery(db: Session, notification: Notification) -> None:
    if not settings.SMTP_HOST:
        notification.status = NotificationStatus.SKIPPED_NOT_CONFIGURED
        notification.error_message = "SMTP is not configured for this deployment."
        return

    notification.attempt_count += 1
    notification.last_attempt_at = datetime.now(UTC)

    incident = db.get(Incident, notification.incident_id)
    recipient = (
        db.get(User, notification.recipient_user_id) if notification.recipient_user_id else None
    )
    if incident is None or recipient is None:
        notification.status = NotificationStatus.FAILED
        notification.error_message = "Incident or recipient no longer exists."
        return

    try:
        _send_email(recipient.email, incident)
        notification.status = NotificationStatus.SENT
        notification.error_message = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email delivery failed for notification %s: %s", notification.id, exc)
        notification.error_message = str(exc)
        if notification.attempt_count >= _MAX_ATTEMPTS:
            notification.status = NotificationStatus.FAILED
        else:
            backoff_index = min(notification.attempt_count - 1, len(_RETRY_BACKOFF_MINUTES) - 1)
            delay = timedelta(minutes=_RETRY_BACKOFF_MINUTES[backoff_index])
            notification.next_attempt_at = datetime.now(UTC) + delay


def _send_email(to_address: str, incident: Incident) -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")

    review_url = f"{settings.PUBLIC_BASE_URL}/incidents?id={incident.id}"
    category_label = incident.category.value.replace("_", " ")
    subject = f"SmartVision alert: {category_label} ({incident.severity.value})"
    body = (
        f"A {category_label} incident was flagged for human review.\n\n"
        f"Severity: {incident.severity.value}\n"
        f"Camera ID: {incident.camera_id}\n"
        f"Detected at: {incident.event_started_at.isoformat()}\n\n"
        f"Review it here: {review_url}\n\n"
        "This is an automated alert from a decision-support prototype. "
        "It requires human review before any action is taken."
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        settings.SMTP_FROM_ADDRESS or settings.SMTP_USERNAME or "smartvision@localhost"
    )
    message["To"] = to_address
    message.set_content(body)

    if settings.SMTP_USE_TLS:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)


async def notification_worker_loop(session_factory) -> None:
    """Background asyncio task, started from the FastAPI lifespan (see
    app/main.py). Runs forever until cancelled at shutdown."""
    import asyncio

    logger.info("Notification worker started (polling every %ss)", WORKER_POLL_INTERVAL_SECONDS)
    while True:
        try:
            with session_factory() as db:
                count = process_pending_notifications(db)
                if count:
                    logger.info("Notification worker processed %d pending email(s)", count)
        except Exception:
            logger.exception("Notification worker iteration failed")
        await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
