"""Draws detection/track overlays onto a frame for the live annotated feed.

Kept separate from detection/tracking so it can be unit-tested on its own
(does this drawing call crash on an empty track list? on an out-of-bounds
box?) without needing a model loaded.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision_worker.types import Track

_BOX_COLOR = (48, 209, 189)  # BGR -- matches the dashboard's teal accent
_TEXT_COLOR = (230, 237, 243)
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def annotate_frame(frame_bgr: np.ndarray, tracks: list[Track]) -> np.ndarray:
    """Returns a new frame (does not mutate the input) with bounding boxes
    and `<class> #<track_id>` labels drawn for each active track."""
    annotated = frame_bgr.copy()
    h, w = annotated.shape[:2]

    for track in tracks:
        x1 = max(0, min(int(track.box.x1), w - 1))
        y1 = max(0, min(int(track.box.y1), h - 1))
        x2 = max(0, min(int(track.box.x2), w - 1))
        y2 = max(0, min(int(track.box.y2), h - 1))
        if x2 <= x1 or y2 <= y1:
            continue

        cv2.rectangle(annotated, (x1, y1), (x2, y2), _BOX_COLOR, 2)
        label = f"{track.class_name} #{track.track_id} ({track.confidence:.0%})"
        (text_w, text_h), _ = cv2.getTextSize(label, _FONT, 0.5, 1)
        label_y1 = max(0, y1 - text_h - 6)
        cv2.rectangle(annotated, (x1, label_y1), (x1 + text_w + 6, y1), _BOX_COLOR, -1)
        cv2.putText(annotated, label, (x1 + 3, y1 - 4), _FONT, 0.5, (10, 14, 20), 1, cv2.LINE_AA)

    return annotated


def encode_jpeg(frame_bgr: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode frame")
    return buf.tobytes()
