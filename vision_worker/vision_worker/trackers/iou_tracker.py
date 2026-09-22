"""A lightweight, per-camera, IoU-based multi-object tracker.

This is intentionally simple: greedy IoU matching between the previous
frame's tracks and the current frame's detections, with a "missed frames"
grace period before a track is dropped. It is not the ByteTrack algorithm
from the paper (no Kalman-filter motion prediction, no two-stage
high/low-confidence association) -- it's a correct, well-tested SORT-style
baseline that satisfies the same functional need (stable per-object IDs
across frames) without pulling in a heavier dependency. Swapping in a full
ByteTrack implementation later only touches this one file, since the rest
of the pipeline only depends on the `Tracker` interface below.

Tracking is per-camera and resets whenever a camera reconnects -- there is
no cross-camera identity matching anywhere in this codebase, by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from vision_worker.types import BoundingBox, Detection, Track

#: How many consecutive frames a track may go undetected before being
#: dropped. Tunable per deployment; kept as a constructor arg, not a
#: global, so each camera worker can use its own value if needed.
DEFAULT_MAX_MISSED_FRAMES = 15

#: Minimum IoU for a detection to be matched to an existing track.
DEFAULT_IOU_MATCH_THRESHOLD = 0.3

#: How many recent footpoints to retain per track (bounds memory; used by
#: dwell-time and stationarity checks, which only need a short window).
FOOTPOINT_HISTORY_LEN = 90


@dataclass
class _MatchResult:
    matched_track_ids: set[int]
    matched_detection_indices: set[int]


class IoUTracker:
    """Stateful tracker for a single camera. Call `update()` once per
    processed frame with that frame's detections."""

    def __init__(
        self,
        max_missed_frames: int = DEFAULT_MAX_MISSED_FRAMES,
        iou_match_threshold: float = DEFAULT_IOU_MATCH_THRESHOLD,
    ) -> None:
        self._max_missed_frames = max_missed_frames
        self._iou_match_threshold = iou_match_threshold
        self._tracks: dict[int, Track] = {}
        self._next_track_id = 1
        self._frame_index = 0

    @property
    def active_tracks(self) -> list[Track]:
        return list(self._tracks.values())

    def reset(self) -> None:
        """Clear all state. Called when a camera reconnects after a drop --
        tracks from before a gap are not carried forward, since we have no
        way to know they're still the same objects."""
        self._tracks.clear()
        self._next_track_id = 1
        self._frame_index = 0

    def update(self, detections: list[Detection]) -> list[Track]:
        self._frame_index += 1
        match = self._match(detections)

        # Update matched tracks.
        for det_idx, detection in enumerate(detections):
            track_id = self._detection_to_track.get(det_idx)
            if track_id is None:
                continue
            track = self._tracks[track_id]
            track.box = detection.box
            track.confidence = detection.confidence
            track.class_name = detection.class_name
            track.last_seen_frame = self._frame_index
            track.missed_frames = 0
            track.footpoint_history.append(detection.box.footpoint)
            if len(track.footpoint_history) > FOOTPOINT_HISTORY_LEN:
                track.footpoint_history = track.footpoint_history[-FOOTPOINT_HISTORY_LEN:]

        # Age and drop unmatched tracks.
        for track_id in list(self._tracks.keys()):
            if track_id in match.matched_track_ids:
                continue
            track = self._tracks[track_id]
            track.missed_frames += 1
            if track.missed_frames > self._max_missed_frames:
                del self._tracks[track_id]

        # Start new tracks for unmatched detections.
        for det_idx, detection in enumerate(detections):
            if det_idx in match.matched_detection_indices:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = Track(
                track_id=track_id,
                class_name=detection.class_name,
                box=detection.box,
                confidence=detection.confidence,
                first_seen_frame=self._frame_index,
                last_seen_frame=self._frame_index,
                footpoint_history=[detection.box.footpoint],
                missed_frames=0,
            )

        return self.active_tracks

    def _match(self, detections: list[Detection]) -> _MatchResult:
        """Greedy best-IoU matching, highest-IoU pairs first. Only matches
        within the same class -- a person should never be matched onto a
        backpack's previous track just because the boxes overlap."""
        self._detection_to_track: dict[int, int] = {}
        candidates: list[tuple[float, int, int]] = []  # (iou, track_id, det_idx)

        for track_id, track in self._tracks.items():
            for det_idx, detection in enumerate(detections):
                if detection.class_name != track.class_name:
                    continue
                iou = _iou(track.box, detection.box)
                if iou >= self._iou_match_threshold:
                    candidates.append((iou, track_id, det_idx))

        candidates.sort(key=lambda c: c[0], reverse=True)

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        for _iou_value, track_id, det_idx in candidates:
            if track_id in matched_tracks or det_idx in matched_detections:
                continue
            matched_tracks.add(track_id)
            matched_detections.add(det_idx)
            self._detection_to_track[det_idx] = track_id

        return _MatchResult(
            matched_track_ids=matched_tracks,
            matched_detection_indices=matched_detections,
        )


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    return a.iou(b)
