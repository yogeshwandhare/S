"""Frame-level OpenAI CLIP zero-shot classifier used for violence triage.

This follows the public violence-detection repository's CLIP ViT-B/32 and
text-prompt approach. Its cosine similarity is a ranking score, not a
calibrated probability; all resulting incidents require human review.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

DEFAULT_LABELS = [
    "people walking on a street",
    "buildings",
    "fight on a street",
    "fire on a street",
    "street violence",
    "road",
    "car crash",
    "cars on a road",
    "car parking area",
    "cars",
    "office environment",
    "office corridor",
    "violence in office",
    "fire in office",
    "people talking",
    "people walking in office",
    "person walking in office",
    "group of people",
]


@dataclass(frozen=True)
class ViolencePrediction:
    label: str
    similarity: float


class ClipViolenceClassifier:
    """OpenAI CLIP ViT-B/32 zero-shot scene classifier."""

    def __init__(
        self,
        labels: list[str] | None = None,
        device: str = "cpu",
    ) -> None:
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "OpenCLIP is not installed. Install the vision worker's 'violence' extra."
            ) from exc

        self._torch = torch
        self._labels = labels or DEFAULT_LABELS
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32-quickgelu", pretrained="openai"
        )
        self._model.to(device)
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")
        prompts = [f"a photo of {label}" for label in self._labels]
        with torch.inference_mode():
            tokens = self._tokenizer(prompts).to(device)
            text_features = self._model.encode_text(tokens)
            self._text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    def predict(self, frame_bgr: np.ndarray) -> ViolencePrediction:
        from PIL import Image

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._preprocess(Image.fromarray(rgb)).unsqueeze(0)
        device = next(self._model.parameters()).device
        with self._torch.inference_mode():
            image_features = self._model.encode_image(image.to(device))
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            similarities = image_features @ self._text_features.T
            index = int(similarities[0].argmax().item())
            score = float(similarities[0, index].item())
        return ViolencePrediction(label=self._labels[index], similarity=score)
