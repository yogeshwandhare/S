"""Optional YOLO adapter via the `ultralytics` package.

License: AGPL-3.0-only. This adapter exists because the project brief
explicitly allows it as an opt-in choice for users who accept the AGPL-3.0
obligations that come with it -- it is never enabled by default, and
enabling it is a deliberate action recorded in the model registry (see
``docs/MODEL_REGISTRY.md`` and ``ModelConfig.license`` in the database).

Default checkpoint: ``yolo11n.pt`` (the smallest, most broadly-supported
Ultralytics checkpoint at the time this was written). ``yolo26n.pt`` is
also selectable -- both are downloaded automatically from
``github.com/ultralytics/assets`` releases on first use.
"""

from __future__ import annotations

import logging

import numpy as np

from vision_worker.detectors.base import Detector, DetectorUnavailableError
from vision_worker.types import BoundingBox, Detection

logger = logging.getLogger(__name__)


class YoloDetector(Detector):
    name = "YOLO (Ultralytics)"
    license = "AGPL-3.0-only"

    def __init__(self, checkpoint: str = "yolo11n.pt") -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorUnavailableError(
                "The 'ultralytics' package is not installed. This is the opt-in "
                "AGPL-3.0 adapter -- install the backend's 'yolo' optional "
                "dependency group and enable it explicitly in Settings to use it."
            ) from exc

        try:
            self._model = YOLO(checkpoint)
        except Exception as exc:
            raise DetectorUnavailableError(
                f"YOLO checkpoint '{checkpoint}' could not be loaded or downloaded: {exc}"
            ) from exc

        self.checkpoint = checkpoint
        self._class_names: dict[int, str] = dict(self._model.names)

    @property
    def class_names(self) -> dict[int, str]:
        return dict(self._class_names)

    def detect(self, frame_bgr: np.ndarray, confidence_threshold: float) -> list[Detection]:
        # Ultralytics accepts BGR numpy arrays directly (OpenCV convention) --
        # no channel conversion needed, unlike the RF-DETR adapter.
        # .predict() is typed loosely (it can also stream), so materialize
        # it as a concrete list before indexing.
        results = list(self._model.predict(frame_bgr, conf=confidence_threshold, verbose=False))
        if not results:
            return []

        result = results[0]
        detections: list[Detection] = []
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        for i in range(len(boxes)):
            x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[i].tolist())
            confidence = float(boxes.conf[i])
            class_id = int(boxes.cls[i])
            class_name = self._class_names.get(class_id, f"class_{class_id}")
            detections.append(
                Detection(
                    box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                )
            )
        return detections
