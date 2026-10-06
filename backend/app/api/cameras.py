from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require_admin, require_any_role, require_operator_or_admin
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.enums import CameraStatus
from app.models.user import User
from app.schemas.camera import (
    CameraCreate,
    CameraHealthRead,
    CameraRead,
    CameraUpdate,
    UsbDeviceInfo,
    UsbDevicesRead,
)
from app.services.video_storage import resolve_video_source

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

_MJPEG_BOUNDARY = "smartvisionframe"
_MAX_VIDEO_UPLOAD_BYTES = 500 * 1024 * 1024


def _get_camera_or_404(db: Session, camera_id: uuid.UUID) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


def _apply_live_status(camera: Camera, request: Request) -> Camera:
    """Overlay the camera's *live* connection status (from the running
    worker, if any) onto the ORM object before it's serialized. This is
    intentionally not persisted to the database -- `status` in storage
    reflects the last-known state at write time, but what the dashboard
    should show right now is whatever the camera manager currently reports,
    not a column that would otherwise go stale between health checks."""
    manager = getattr(request.app.state, "camera_manager", None)
    if manager is None or not camera.enabled:
        camera.status = CameraStatus.DISABLED if not camera.enabled else CameraStatus.OFFLINE
        return camera

    health = manager.get_health(camera.id)
    if health is None:
        camera.status = CameraStatus.OFFLINE
    elif health.connected:
        camera.status = CameraStatus.ONLINE
    elif health.last_error:
        camera.status = CameraStatus.ERROR
    else:
        camera.status = CameraStatus.OFFLINE
    return camera


@router.get("", response_model=list[CameraRead])
def list_cameras(
    request: Request, db: Session = Depends(get_db), _user: User = Depends(require_any_role)
) -> list[Camera]:
    cameras = list(db.scalars(select(Camera).order_by(Camera.created_at)))
    return [_apply_live_status(c, request) for c in cameras]


@router.post("/upload-video")
async def upload_camera_video(
    video: UploadFile = File(...),
    _user: User = Depends(require_admin),
) -> dict[str, str]:
    """Store a local MP4 for use as a file-backed camera source."""
    original_name = Path(video.filename or "video.mp4").name
    if Path(original_name).suffix.lower() != ".mp4":
        raise HTTPException(status_code=400, detail="Please select an MP4 video file")

    upload_dir = Path(get_settings().EVIDENCE_STORAGE_DIR) / "camera_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}.mp4"
    destination = upload_dir / stored_name
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_VIDEO_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video must be 500 MB or smaller")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await video.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The selected video is empty")

    return {
        "source_uri": f"uploads/{stored_name}",
        "original_filename": original_name,
    }


@router.post("", response_model=CameraRead, status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Camera:
    camera = Camera(
        name=payload.name,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
        inference_fps=payload.inference_fps,
        target_width=payload.target_width,
        notes=payload.notes,
        status=CameraStatus.OFFLINE,
        enabled=True,
    )
    db.add(camera)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="camera_created",
            resource_type="camera",
            resource_id=str(camera.id),
            detail=f"name={payload.name} source_type={payload.source_type.value}",
        )
    )
    db.commit()
    db.refresh(camera)

    manager = getattr(request.app.state, "camera_manager", None)
    if manager is not None and camera.enabled:
        manager.start_camera(camera, db)

    return _apply_live_status(camera, request)


@router.get("/usb-devices", response_model=UsbDevicesRead)
def list_usb_devices(_user: User = Depends(require_operator_or_admin)) -> UsbDevicesRead:
    bridge = os.environ.get("USB_CAMERA_BRIDGE_URL", "").strip()
    if not bridge:
        return UsbDevicesRead(discovery_available=False, devices=[])
    try:
        response = httpx.get(f"{bridge.rstrip('/')}/devices", timeout=4, trust_env=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Invalid device list")
        devices = [UsbDeviceInfo.model_validate(device) for device in data]
        return UsbDevicesRead(discovery_available=True, devices=devices)
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Camera discovery is unavailable. Start the Windows camera bridge and retry.",
        ) from None


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(
    camera_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> Camera:
    camera = _get_camera_or_404(db, camera_id)
    return _apply_live_status(camera, request)


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: uuid.UUID,
    payload: CameraUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Camera:
    camera = _get_camera_or_404(db, camera_id)
    changes = payload.model_dump(exclude_unset=True)
    device_index = changes.pop("usb_device_index", None)
    if device_index is not None:
        if camera.source_type.value != "usb":
            raise HTTPException(status_code=422, detail="Device selection is only for USB cameras")
        changes["source_uri"] = str(device_index)
    for field, value in changes.items():
        setattr(camera, field, value)

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="camera_updated",
            resource_type="camera",
            resource_id=str(camera.id),
            detail=str(changes),
        )
    )
    db.commit()
    db.refresh(camera)

    manager = getattr(request.app.state, "camera_manager", None)
    if manager is not None:
        if camera.enabled:
            manager.start_camera(camera, db)  # restarts with new config if already running
        else:
            manager.stop_camera(str(camera.id))

    return _apply_live_status(camera, request)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> None:
    camera = _get_camera_or_404(db, camera_id)

    manager = getattr(request.app.state, "camera_manager", None)
    if manager is not None:
        manager.stop_camera(str(camera.id))

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="camera_deleted",
            resource_type="camera",
            resource_id=str(camera.id),
            detail=f"name={camera.name}",
        )
    )
    db.delete(camera)
    db.commit()


@router.post("/{camera_id}/test-connection")
def test_camera_connection(
    camera_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_or_admin),
) -> dict:
    """Briefly opens the source to check reachability, without starting a
    persistent worker. Used by the "Test connection" button in the Cameras
    UI."""
    camera = _get_camera_or_404(db, camera_id)

    import os

    from vision_worker.pipeline.source import CameraConnectionError, FrameSource, FrameSourceConfig
    from vision_worker.pipeline.source import SourceType as VwSourceType

    uri = camera.source_uri
    if camera.source_type.value == "file":
        uri = resolve_video_source(uri)

    source = FrameSource(
        FrameSourceConfig(source_type=VwSourceType(camera.source_type.value), uri=uri)
    )
    try:
        source.open()
        frame = source.read()
        ok = frame is not None
        message = "Connected and read a frame" if ok else "Opened but no frame read"
        return {"ok": ok, "message": message}
    except CameraConnectionError as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        source.close()


@router.get("/{camera_id}/health", response_model=CameraHealthRead)
def get_camera_health(
    camera_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> CameraHealthRead:
    camera = _get_camera_or_404(db, camera_id)
    manager = getattr(request.app.state, "camera_manager", None)
    health = manager.get_health(camera.id) if manager else None

    if health is None or manager is None:
        return CameraHealthRead(
            camera_id=camera.id,
            connected=False,
            last_frame_at=None,
            last_error="Camera worker is not running" if camera.enabled else "Camera is disabled",
            measured_capture_fps=0.0,
            measured_inference_fps=0.0,
            consecutive_reconnect_attempts=0,
            active_track_count=0,
        )

    worker = manager.get_worker(camera.id)
    track_count = len(worker.get_active_tracks()) if worker else 0
    return CameraHealthRead(
        camera_id=camera.id,
        connected=health.connected,
        last_frame_at=health.last_frame_at,
        last_error=health.last_error,
        measured_capture_fps=health.measured_capture_fps,
        measured_inference_fps=health.measured_inference_fps,
        consecutive_reconnect_attempts=health.consecutive_reconnect_attempts,
        active_track_count=track_count,
    )


@router.get("/{camera_id}/stream.mjpg")
def stream_camera(
    camera_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(require_any_role),
) -> StreamingResponse:
    """MJPEG live view -- the documented MVP streaming approach (see
    docs/LIMITATIONS.md for why: simple, broadly browser-compatible via a
    plain <img> tag, at the cost of more bandwidth than WebRTC for many
    simultaneous high-resolution viewers)."""
    camera = _get_camera_or_404(db, camera_id)
    manager = getattr(request.app.state, "camera_manager", None)
    if manager is None or not manager.is_running(camera.id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Camera is not currently running",
        )

    def generate():
        worker = manager.get_worker(camera.id)
        last_sent: bytes | None = None
        while True:
            if worker is None or not manager.is_running(camera.id):
                break
            frame = worker.get_latest_jpeg()
            if frame is not None and frame != last_sent:
                last_sent = frame
                yield (
                    b"--" + _MJPEG_BOUNDARY.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(0.05)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY}",
    )
