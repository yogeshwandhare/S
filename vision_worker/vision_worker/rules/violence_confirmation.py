"""Consecutive-frame confirmation for CLIP violence scene predictions."""

from __future__ import annotations

from dataclasses import dataclass

from vision_worker.detectors.clip_violence_classifier import ViolencePrediction

VIOLENCE_LABELS = frozenset({"fight on a street", "street violence", "violence in office"})


@dataclass
class ViolenceConfirmationConfig:
    minimum_similarity: float = 0.23
    min_consecutive_frames: int = 3
    cooldown_seconds: float = 60.0
    severity: str = "high"


@dataclass(frozen=True)
class ViolenceEvent:
    label: str
    similarity: float
    consecutive_frames: int
    severity: str


class ViolenceConfirmationRule:
    def __init__(self, config: ViolenceConfirmationConfig | None = None) -> None:
        self.config = config or ViolenceConfirmationConfig()
        self._label: str | None = None
        self._streak = 0
        self._last_triggered_at: float | None = None

    def evaluate(self, prediction: ViolencePrediction, now: float) -> list[ViolenceEvent]:
        if (
            prediction.label not in VIOLENCE_LABELS
            or prediction.similarity < self.config.minimum_similarity
        ):
            self._label = None
            self._streak = 0
            return []

        if prediction.label == self._label:
            self._streak += 1
        else:
            self._label = prediction.label
            self._streak = 1

        if self._streak < self.config.min_consecutive_frames:
            return []
        if (
            self._last_triggered_at is not None
            and now - self._last_triggered_at < self.config.cooldown_seconds
        ):
            return []

        self._last_triggered_at = now
        return [
            ViolenceEvent(
                label=prediction.label,
                similarity=prediction.similarity,
                consecutive_frames=self._streak,
                severity=self.config.severity,
            )
        ]
