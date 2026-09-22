from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.enums import CameraSourceType, CameraStatus
from app.models.user import User
from app.schemas.camera import CameraRead

router = APIRouter(prefix="/api/demo", tags=["demo"])

_SAMPLE_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "sample_data")
)

_KNOWN_CLIPS = {
    "synthetic_pipeline_test.mp4": (
        "A single real photograph (people + a bus), held static across 20 frames. "
        "Not live CCTV footage -- used to demonstrate detection and tracking "
        "without requiring camera hardware."
    ),
}


class SampleVideo(BaseModel):
    filename: str
    description: str


class DemoLaunchRequest(BaseModel):
    filename: str
    camera_name: str = "Demo Camera"


@router.get("/sample-videos", response_model=list[SampleVideo])
def list_sample_videos(_user: User = Depends(require_admin)) -> list[SampleVideo]:
    """Only .mp4 files actually present on disk are ever listed -- never a
    hardcoded catalog that might not match what's really there."""
    if not os.path.isdir(_SAMPLE_DATA_DIR):
        return []
    videos = []
    for filename in sorted(os.listdir(_SAMPLE_DATA_DIR)):
        if filename.endswith(".mp4"):
            videos.append(
                SampleVideo(
                    filename=filename,
                    description=_KNOWN_CLIPS.get(
                        filename, "Sample clip under sample_data/ -- see sample_data/README.md."
                    ),
                )
            )
    return videos


@router.post("", response_model=CameraRead, status_code=status.HTTP_201_CREATED)
def launch_demo(
    payload: DemoLaunchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Camera:
    """Creates a camera against a sample video, clearly labeled as a demo
    in its notes field -- this is the only thing that distinguishes it from
    an ordinary file-source camera, since under the hood it's exactly that.
    """
    if ".." in payload.filename or "/" in payload.filename or "\\" in payload.filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample video not found")

    video_path = os.path.join(_SAMPLE_DATA_DIR, payload.filename)
    if not os.path.isfile(video_path) or not payload.filename.endswith(".mp4"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample video not found")

    camera = Camera(
        name=payload.camera_name,
        source_type=CameraSourceType.FILE,
        source_uri=payload.filename,
        status=CameraStatus.OFFLINE,
        enabled=True,
        notes=f"DEMO MODE -- sample video ({payload.filename}), not a real camera.",
    )
    db.add(camera)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="demo_camera_launched",
            resource_type="camera",
            resource_id=str(camera.id),
            detail=f"sample_video={payload.filename}",
        )
    )
    db.commit()
    db.refresh(camera)

    manager = getattr(request.app.state, "camera_manager", None)
    if manager is not None:
        manager.start_camera(camera, db)

    return camera
