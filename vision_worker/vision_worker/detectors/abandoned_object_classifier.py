"""Ultralytics classification adapter for abandoned-object candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

ABANDONED_LABEL_MARKERS = ("abandon", "unattend", "suspicious", "leftbehind", "left behind")
LUGGAGE_LABELS = frozenset({"bag", "backpack", "handbag", "suitcase", "luggage"})


def is_luggage_label(label: str) -> bool:
    normalized = " ".join(label.casefold().replace("_", " ").replace("-", " ").split())
    return normalized in LUGGAGE_LABELS or any(
        marker in normalized for marker in ABANDONED_LABEL_MARKERS
    )


@dataclass(frozen=True)
class AbandonedObjectClassification:
    label: str
    confidence: float
    is_luggage: bool


class YoloAbandonedObjectClassifier:
    """Runs the upstream YOLO11 classification checkpoint on a bag crop."""

    name = "Abandoned Object Classifier (YOLO11 classification)"

    def __init__(self, checkpoint_path: str) -> None:
        checkpoint = Path(checkpoint_path)
        if not checkpoint.is_file():
            raise FileNotFoundError(f"Abandoned-object checkpoint not found: {checkpoint}")

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Install the optional YOLO dependencies to use this model.") from exc

        self._model = YOLO(str(checkpoint))
        if getattr(self._model, "task", None) != "classify":
            raise ValueError("Expected an Ultralytics classification checkpoint (task='classify').")

        names = self._model.names
        self.class_names = {int(class_id): str(name) for class_id, name in names.items()}
        self.positive_labels = frozenset(
            label for label in self.class_names.values() if is_luggage_label(label)
        )
        if not self.positive_labels:
            raise ValueError(
                "Checkpoint has no recognizable luggage class (bag, backpack, "
                "handbag, suitcase, or luggage). "
                f"Found: {', '.join(self.class_names.values())}"
            )

    def classify(self, crop_bgr: np.ndarray) -> AbandonedObjectClassification:
        results = list(self._model.predict(crop_bgr, verbose=False))
        if not results or results[0].probs is None:
            raise RuntimeError("YOLO classification checkpoint returned no class probabilities.")

        probs = results[0].probs
        class_id = int(probs.top1)
        label = self.class_names.get(class_id, f"class_{class_id}")
        confidence = float(probs.top1conf)
        return AbandonedObjectClassification(
            label=label,
            confidence=confidence,
            is_luggage=label in self.positive_labels,
        )
