"""Weapon detector adapter.

Unlike the general object detector (RF-DETR/YOLO), there is no off-the-
shelf pretrained weapon-detection checkpoint with clear licensing and
provenance -- see docs/MODEL_REGISTRY.md for what was actually
investigated. This adapter loads a checkpoint fine-tuned by
`scripts/weapon_detection/train.py` on the Sohas dataset
(ari-dasci/OD-WeaponDetection, CC BY-SA 4.0) and exported to ONNX by
`scripts/weapon_detection/export_onnx.py`, and runs it via ONNX Runtime
(this project's optimized-inference stack).

If no exported checkpoint exists at the configured path, `__init__` raises
`DetectorUnavailableError` -- the camera pipeline then runs with weapon
detection disabled and the dashboard shows "Weapon model not configured",
exactly as the project brief requires. This adapter is never used to
fabricate a detection.

Because the checkpoint was produced by fine-tuning with `ultralytics`
(AGPL-3.0), it is treated the same way as the optional YOLO object-
detection adapter: disabled by default, enabled only via the same explicit
AGPL-3.0 acknowledgement in `scripts/download_models.py`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from vision_worker.detectors.base import Detector, DetectorUnavailableError
from vision_worker.types import BoundingBox, Detection

logger = logging.getLogger(__name__)

_DEFAULT_CLASS_NAMES = ["pistol", "smartphone", "knife", "monedero", "billete", "tarjeta"]
#: Classes that actually count as a weapon for alerting purposes -- the
#: rest exist only as hard-negative examples (phones, purses, banknotes,
#: cards) so the model learns NOT to confuse them with a weapon.
WEAPON_CLASSES = frozenset({"pistol", "knife"})


class WeaponDetector(Detector):
    name = "Weapon Detector (fine-tuned YOLO11n, ONNX)"
    license = (
        "AGPL-3.0-only (training framework); dataset CC BY-SA 4.0 (ari-dasci/OD-WeaponDetection)"
    )

    def __init__(
        self, onnx_path: str, imgsz: int = 320, class_names: list[str] | None = None
    ) -> None:
        if not Path(onnx_path).exists():
            raise DetectorUnavailableError(
                f"Weapon detection checkpoint not found at {onnx_path}. Train one with "
                "scripts/weapon_detection/train.py and export it with "
                "scripts/weapon_detection/export_onnx.py, then register it -- see "
                "docs/MODEL_REGISTRY.md."
            )

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise DetectorUnavailableError("The 'onnxruntime' package is not installed.") from exc

        try:
            self._session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001
            raise DetectorUnavailableError(
                f"Failed to load weapon detector ONNX model: {exc}"
            ) from exc

        self._imgsz = imgsz
        self._class_names_list = class_names or _DEFAULT_CLASS_NAMES
        self._input_name = self._session.get_inputs()[0].name

    @property
    def class_names(self) -> dict[int, str]:
        return dict(enumerate(self._class_names_list))

    def detect(self, frame_bgr: np.ndarray, confidence_threshold: float) -> list[Detection]:
        orig_h, orig_w = frame_bgr.shape[:2]
        blob = self._preprocess(frame_bgr)
        raw_output = self._session.run(None, {self._input_name: blob})[0]
        return self._postprocess(raw_output, orig_w, orig_h, confidence_threshold)

    def _preprocess(self, frame_bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame_bgr, (self._imgsz, self._imgsz))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        chw = normalized.transpose(2, 0, 1)
        return np.expand_dims(chw, axis=0)

    def _postprocess(
        self, raw_output: np.ndarray, orig_w: int, orig_h: int, confidence_threshold: float
    ) -> list[Detection]:
        # Ultralytics ONNX export shape: (1, 4 + num_classes, num_boxes),
        # boxes in (cx, cy, w, h) at model input resolution.
        predictions = raw_output[0].T
        num_classes = len(self._class_names_list)

        boxes = predictions[:, :4]
        class_scores = predictions[:, 4 : 4 + num_classes]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]

        keep = confidences >= confidence_threshold
        boxes, class_ids, confidences = boxes[keep], class_ids[keep], confidences[keep]

        if len(boxes) == 0:
            return []

        scale_x, scale_y = orig_w / self._imgsz, orig_h / self._imgsz
        indices = self._nms(boxes, confidences, iou_threshold=0.45)

        detections: list[Detection] = []
        for i in indices:
            cx, cy, w, h = boxes[i]
            x1 = (cx - w / 2) * scale_x
            y1 = (cy - h / 2) * scale_y
            x2 = (cx + w / 2) * scale_x
            y2 = (cy + h / 2) * scale_y
            class_id = int(class_ids[i])
            class_name = (
                self._class_names_list[class_id]
                if class_id < len(self._class_names_list)
                else f"class_{class_id}"
            )
            detections.append(
                Detection(
                    box=BoundingBox(x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2)),
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(confidences[i]),
                )
            )
        return detections

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
        """Standard greedy non-max suppression on (cx, cy, w, h) boxes."""
        if len(boxes) == 0:
            return []
        x1 = boxes[:, 0] - boxes[:, 2] / 2
        y1 = boxes[:, 1] - boxes[:, 3] / 2
        x2 = boxes[:, 0] + boxes[:, 2] / 2
        y2 = boxes[:, 1] + boxes[:, 3] / 2
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while len(order) > 0:
            i = order[0]
            keep.append(int(i))
            if len(order) == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou <= iou_threshold]
        return keep
