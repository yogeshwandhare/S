"""Builds a `vision_worker.Detector` from whatever the model registry says
is currently enabled + available -- the backend never hardcodes which
detector to use. If nothing is enabled and available, returns None, and
callers (the camera worker manager) serve the raw feed with no detection
overlay rather than crashing or fabricating output.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ModelTask
from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)

# Maps a model_configs.name value to the vision_worker adapter that loads it.
_ADAPTER_BUILDERS = {}


def _build_rfdetr_nano():
    from vision_worker.detectors.rfdetr_detector import RFDetrNanoDetector

    return RFDetrNanoDetector()


def _build_yolo(checkpoint: str = "yolo11n.pt"):
    from vision_worker.detectors.yolo_detector import YoloDetector

    return YoloDetector(checkpoint=checkpoint)


_ADAPTER_BUILDERS["rf-detr-nano"] = _build_rfdetr_nano
_ADAPTER_BUILDERS["yolo11n"] = lambda: _build_yolo("yolo11n.pt")
_ADAPTER_BUILDERS["yolo26n"] = lambda: _build_yolo("yolo26n.pt")


def get_active_object_detector(db: Session):
    """Returns a loaded Detector instance for the currently enabled +
    available object-detection model, or None if none is configured.

    Loading a real model can be slow (seconds) and memory-heavy -- callers
    (the camera manager) should call this once at startup/config-change
    time and reuse the instance across all cameras, never per-frame.
    """
    config = db.scalar(
        select(ModelConfig)
        .where(ModelConfig.task == ModelTask.OBJECT_DETECTION)
        .where(ModelConfig.enabled.is_(True))
        .where(ModelConfig.is_available.is_(True))
        .order_by(ModelConfig.updated_at.desc())
    )
    if config is None:
        logger.info("No enabled + available object-detection model in the registry.")
        return None

    builder = _ADAPTER_BUILDERS.get(config.name)
    if builder is None:
        logger.error("Model registry entry %r has no known adapter.", config.name)
        return None

    try:
        return builder()
    except Exception:
        logger.exception("Failed to load detector %r despite being marked available.", config.name)
        return None


def get_active_weapon_detector(db: Session):
    """Same idea as `get_active_object_detector`, for the weapon-detection
    task. Unlike the general detectors, the weapon detector's checkpoint
    doesn't auto-download -- it's produced locally by
    scripts/weapon_detection/train.py + export_onnx.py, and its filesystem
    path is read from the registry row's `checkpoint_path` column."""
    config = db.scalar(
        select(ModelConfig)
        .where(ModelConfig.task == ModelTask.WEAPON_DETECTION)
        .where(ModelConfig.enabled.is_(True))
        .where(ModelConfig.is_available.is_(True))
        .order_by(ModelConfig.updated_at.desc())
    )
    if config is None:
        logger.info("No enabled + available weapon-detection model in the registry.")
        return None

    if not config.checkpoint_path:
        logger.error("Weapon detection registry entry has no checkpoint_path set.")
        return None

    try:
        from vision_worker.detectors.weapon_detector import WeaponDetector

        return WeaponDetector(onnx_path=config.checkpoint_path)
    except Exception:
        logger.exception("Failed to load weapon detector despite being marked available.")
        return None
