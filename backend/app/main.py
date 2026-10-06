from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import (
    analytics,
    audit_logs,
    auth,
    cameras,
    demo,
    health,
    incidents,
    models,
    notifications,
    users,
    zones,
)
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.camera import Camera
from app.services.camera_manager import CameraManager
from app.services.detector_factory import (
    get_active_object_detector,
    get_active_violence_classifier,
    get_active_abandoned_object_classifier,
    get_active_weapon_detector,
)
from app.services.incident_service import handle_rule_trigger
from app.services.notification_service import notification_worker_loop

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = CameraManager()
    app.state.camera_manager = manager

    if settings.ENVIRONMENT == "test":
        # The API test suite exercises camera endpoints directly against an
        # isolated per-test database via dependency overrides; it does not
        # want this lifespan's own DB session (bound to the process-wide
        # DATABASE_URL) touching a different database, nor real camera
        # worker threads spun up for fixture data that was never meant to
        # be a real video source. Real deployments (development/production)
        # always run the full startup below.
        yield
        manager.stop_all()
        return

    initialization_stopped = threading.Event()

    def initialize_camera_manager() -> None:
        # Loading ML frameworks and checkpoints can take minutes and use a
        # large amount of memory. Do it off the ASGI startup path so API
        # routes (especially auth and health) are available immediately.
        with SessionLocal() as db:
            try:
                detector = get_active_object_detector(db)
                if initialization_stopped.is_set():
                    return
                manager.set_detector(detector)
                manager.set_weapon_detector(get_active_weapon_detector(db))
                manager.set_violence_classifier(get_active_violence_classifier(db))
                manager.set_abandoned_object_classifier(
                    get_active_abandoned_object_classifier(db)
                )
                manager.set_incident_callback(handle_rule_trigger)
                if detector is None:
                    logger.info(
                        "Starting with no object detector configured -- camera feeds will "
                        "show raw (unannotated) video until one is enabled in the model "
                        "registry. See scripts/download_models.py."
                    )
                enabled_cameras = list(db.scalars(select(Camera).where(Camera.enabled.is_(True))))
                for camera in enabled_cameras:
                    if initialization_stopped.is_set():
                        break
                    try:
                        manager.start_camera(camera, db)
                    except Exception:
                        logger.exception("Failed to start camera %s on startup", camera.id)
            except Exception:
                # A broken model/camera table must never prevent the API itself
                # (auth, health, etc.) from starting.
                logger.exception("Camera manager startup encountered an error")

    initialization_thread = threading.Thread(
        target=initialize_camera_manager,
        name="camera-manager-startup",
        daemon=True,
    )
    initialization_thread.start()

    notification_task = asyncio.create_task(notification_worker_loop(SessionLocal))

    yield

    initialization_stopped.set()
    notification_task.cancel()
    manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "SmartVision decision-support API. This is a prototype for "
            "human-reviewed public-safety alerting -- not a certified "
            "emergency-response system. See /docs for the full API reference."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(cameras.router)
    app.include_router(models.router)
    app.include_router(zones.router)
    app.include_router(incidents.router)
    app.include_router(notifications.router)
    app.include_router(analytics.router)
    app.include_router(users.router)
    app.include_router(audit_logs.router)
    app.include_router(demo.router)

    return app


app = create_app()
