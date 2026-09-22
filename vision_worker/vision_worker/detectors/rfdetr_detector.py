"""RF-DETR Nano adapter -- the default object detector.

Package: ``rfdetr`` (PyPI), by Roboflow. License: Apache-2.0. Checkpoint:
``rf-detr-nano.pth``, COCO-pretrained, hosted at
``https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth``
(downloaded automatically by the package on first construction, cached
under ``~/.roboflow/models`` or ``$RF_HOME``).

Device selection is automatic: the `rfdetr` package detects CUDA and falls
back to CPU with no configuration needed on our side (see
``rfdetr.config.DEVICE``).

Development note: this adapter is written against the real, current
``rfdetr`` package API (verified from the installed package source, not
from memory) but could not be exercised end-to-end in the sandbox this was
developed in, because that sandbox's network egress does not reach
``storage.googleapis.com``. It downloads and runs normally on a machine
with unrestricted internet access -- see ``scripts/download_models.py``.
"""

from __future__ import annotations

import logging

import numpy as np

from vision_worker.detectors.base import Detector, DetectorUnavailableError
from vision_worker.types import BoundingBox, Detection

logger = logging.getLogger(__name__)

_CONFIDENCE_FLOOR = 0.01  # ask the model for everything; we threshold ourselves


class RFDetrNanoDetector(Detector):
    name = "RF-DETR Nano"
    license = "Apache-2.0"

    def __init__(self) -> None:
        try:
            from rfdetr import RFDETRNano
        except ImportError as exc:
            raise DetectorUnavailableError(
                "The 'rfdetr' package is not installed. Install the backend's "
                "'rfdetr' optional dependency group to enable this detector."
            ) from exc

        try:
            self._model = RFDETRNano()
        except Exception as exc:
            raise DetectorUnavailableError(
                f"RF-DETR Nano checkpoint could not be loaded or downloaded: {exc}"
            ) from exc

        self._class_names: dict[int, str] = self._read_class_metadata()

    def _read_class_metadata(self) -> dict[int, str]:
        """Read the checkpoint's own supported classes rather than assuming
        COCO's 80 classes line up 1:1 with class ids -- the project brief
        explicitly requires this."""
        names = getattr(self._model, "class_names", None) or getattr(
            self._model.model, "class_names", None
        )
        if not names:
            logger.warning(
                "RF-DETR Nano checkpoint exposed no class_names metadata; "
                "class names will fall back to the model's raw class_id."
            )
            return {}
        return dict(enumerate(names))

    @property
    def class_names(self) -> dict[int, str]:
        return dict(self._class_names)

    def detect(self, frame_bgr: np.ndarray, confidence_threshold: float) -> list[Detection]:
        # rfdetr expects RGB; OpenCV frames are BGR.
        frame_rgb = frame_bgr[:, :, ::-1]

        detections = self._model.predict(
            frame_rgb, threshold=max(confidence_threshold, _CONFIDENCE_FLOOR)
        )

        results: list[Detection] = []
        class_name_data = None
        if hasattr(detections, "data") and isinstance(detections.data, dict):
            class_name_data = detections.data.get("class_name")

        for i in range(len(detections.xyxy)):
            confidence = float(detections.confidence[i])
            if confidence < confidence_threshold:
                continue
            x1, y1, x2, y2 = (float(v) for v in detections.xyxy[i])
            class_id = int(detections.class_id[i])
            if class_name_data is not None:
                class_name = str(class_name_data[i])
            else:
                class_name = self._class_names.get(class_id, f"class_{class_id}")

            results.append(
                Detection(
                    box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                )
            )
        return results
