"""Detector interface.

Every object-detection backend (RF-DETR, an optional YOLO adapter, or a
future addition) implements this same small interface. The rest of the
pipeline (tracker, rule engine, dashboard) only ever talks to a `Detector`,
never to a specific model library -- this is what lets a model be swapped
without touching anything downstream, per the project brief's modularity
requirement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from vision_worker.types import Detection


class Detector(ABC):
    """A loaded object-detection model ready to run inference on frames."""

    #: Human-readable name shown in the model registry / Settings page.
    name: str
    #: Exact license string, verified against the checkpoint's own source.
    license: str

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray, confidence_threshold: float) -> list[Detection]:
        """Run detection on a single BGR frame (OpenCV convention) and
        return detections at or above `confidence_threshold`."""
        raise NotImplementedError

    @property
    @abstractmethod
    def class_names(self) -> dict[int, str]:
        """The exact class-id -> class-name mapping this checkpoint
        actually supports, read from the checkpoint's own metadata --
        never assumed. See the project brief: 'Read class metadata rather
        than assuming classes.'"""
        raise NotImplementedError


class DetectorUnavailableError(RuntimeError):
    """Raised when a detector adapter is selected but its checkpoint isn't
    downloaded/available. Callers should catch this and surface a clear
    "model not configured" state -- never fall back to fabricated output."""
