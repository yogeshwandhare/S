"""Per-camera background worker.

Runs two threads so a slow detector never blocks frame capture (and a slow
camera never blocks the last successfully-processed frame from being
served):

    capture thread  --(bounded queue, maxsize=1, drop-stale)-->  inference thread

The capture thread just calls `FrameSource.read()` as fast as the source
provides frames and hands the newest one off through a `queue.Queue(maxsize=1)`
that always contains at most the single most recent frame -- if the
inference thread hasn't consumed the previous one yet, it's dropped rather
than queued up, which is exactly the "stale-frame dropping" the project
brief asks for and is what keeps memory bounded on a slow/CPU-only host.

The inference thread pulls frames at its own pace (throttled to the
camera's configured `inference_fps`), runs detection + tracking, and
publishes an annotated JPEG for the live-view endpoint to serve.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vision_worker.detectors.base import Detector, DetectorUnavailableError
from vision_worker.detectors.clip_violence_classifier import (
    ClipViolenceClassifier,
    ViolencePrediction,
)
from vision_worker.detectors.abandoned_object_classifier import YoloAbandonedObjectClassifier
from vision_worker.pipeline.annotate import annotate_frame, encode_jpeg
from vision_worker.pipeline.source import (
    CameraConnectionError,
    FrameSource,
    wait_with_backoff,
)
from vision_worker.rules.abandoned_object import AbandonedObjectRule
from vision_worker.rules.aggressive_motion import AggressiveMotionRule
from vision_worker.rules.events import RuleTriggerEvent
from vision_worker.rules.intrusion import ZoneIntrusionRule
from vision_worker.rules.weapon_confirmation import WeaponConfirmationRule
from vision_worker.rules.violence_confirmation import ViolenceConfirmationRule
from vision_worker.trackers.iou_tracker import IoUTracker
from vision_worker.types import Track

logger = logging.getLogger(__name__)

_MAX_RECONNECT_BACKOFF_LOG_EVERY = 5  # log at most every Nth retry to avoid log spam


@dataclass
class CameraHealth:
    camera_id: str
    connected: bool
    last_frame_at: datetime | None
    last_error: str | None
    measured_capture_fps: float
    consecutive_reconnect_attempts: int
    #: How many inference cycles (detect + track + annotate) actually
    #: completed per second, over the last 5s -- this is the metric that
    #: reflects real detector throughput, distinct from capture_fps (raw
    #: video decode speed, which is typically much higher and bottlenecked
    #: by nothing but I/O once frames are just being dropped as stale).
    measured_inference_fps: float = 0.0


class CameraWorker:
    def __init__(
        self,
        camera_id: str,
        source: FrameSource,
        detector: Detector | None,
        inference_fps: float = 5.0,
        zone_rules: list[ZoneIntrusionRule] | None = None,
        abandoned_object_rule: AbandonedObjectRule | None = None,
        abandoned_object_classifier: YoloAbandonedObjectClassifier | None = None,
        aggressive_motion_rule: AggressiveMotionRule | None = None,
        weapon_detector: Detector | None = None,
        weapon_confirmation_rule: WeaponConfirmationRule | None = None,
        violence_classifier: ClipViolenceClassifier | None = None,
        violence_confirmation_rule: ViolenceConfirmationRule | None = None,
        on_rule_triggered: Callable[[RuleTriggerEvent, bytes], None] | None = None,
    ) -> None:
        self.camera_id = camera_id
        self._source = source
        self._detector = detector
        self._inference_fps = max(0.1, inference_fps)
        self._tracker = IoUTracker()
        self._zone_rules = zone_rules or []
        self._abandoned_object_rule = abandoned_object_rule
        self._abandoned_object_classifier = abandoned_object_classifier
        self._aggressive_motion_rule = aggressive_motion_rule
        self._weapon_detector = weapon_detector
        self._weapon_confirmation_rule = weapon_confirmation_rule
        self._violence_classifier = violence_classifier
        self._violence_confirmation_rule = violence_confirmation_rule
        self._on_rule_triggered = on_rule_triggered

        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._inference_thread: threading.Thread | None = None

        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._latest_tracks: list[Track] = []
        self._health = CameraHealth(
            camera_id=camera_id,
            connected=False,
            last_frame_at=None,
            last_error=None,
            measured_capture_fps=0.0,
            consecutive_reconnect_attempts=0,
        )

    # --- lifecycle -----------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name=f"camera-capture-{self.camera_id}",
            daemon=True,
        )
        self._inference_thread = threading.Thread(
            target=self._inference_loop,
            name=f"camera-inference-{self.camera_id}",
            daemon=True,
        )
        self._capture_thread.start()
        self._inference_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        for t in (self._capture_thread, self._inference_thread):
            if t is not None:
                t.join(timeout=timeout)
        self._source.close()

    # --- public read-only accessors (thread-safe) -----------------------

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def get_health(self) -> CameraHealth:
        with self._lock:
            return CameraHealth(**vars(self._health))

    def get_active_tracks(self) -> list[Track]:
        with self._lock:
            return list(self._latest_tracks)

    # --- capture thread --------------------------------------------------

    def _capture_loop(self) -> None:
        reconnect_attempt = 0
        while not self._stop_event.is_set():
            try:
                self._source.open()
                with self._lock:
                    self._health.connected = True
                    self._health.last_error = None
                    self._health.consecutive_reconnect_attempts = 0
                reconnect_attempt = 0
                self._tracker.reset()  # never carry tracks across a reconnect gap
                self._read_until_disconnected()
            except CameraConnectionError as exc:
                with self._lock:
                    self._health.connected = False
                    self._health.last_error = str(exc)
                    self._health.consecutive_reconnect_attempts = reconnect_attempt + 1
                if reconnect_attempt % _MAX_RECONNECT_BACKOFF_LOG_EVERY == 0:
                    logger.warning("Camera %s: %s (retrying)", self.camera_id, exc)
                wait_with_backoff(reconnect_attempt, sleep_fn=self._interruptible_sleep)
                reconnect_attempt += 1
            finally:
                self._source.close()

    def _read_until_disconnected(self) -> None:
        frame_times: list[float] = []
        while not self._stop_event.is_set():
            frame = self._source.read()
            if frame is None:
                with self._lock:
                    self._health.connected = False
                    self._health.last_error = "Lost connection to source (empty read)"
                return  # back to the outer reconnect loop

            now = time.monotonic()
            frame_times.append(now)
            frame_times = [t for t in frame_times if now - t <= 5.0]

            with self._lock:
                self._health.connected = True
                self._health.last_frame_at = datetime.now(UTC)
                self._health.measured_capture_fps = (
                    len(frame_times) / 5.0 if len(frame_times) > 1 else 0.0
                )

            # Bounded, stale-frame-dropping hand-off: if the inference
            # thread hasn't consumed the previous frame yet, replace it
            # rather than growing the queue.
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                self._frame_queue.put_nowait(frame)

    def _interruptible_sleep(self, seconds: float) -> None:
        self._stop_event.wait(timeout=seconds)

    # --- inference thread ------------------------------------------------

    def _inference_loop(self) -> None:
        min_interval = 1.0 / self._inference_fps
        last_run = 0.0
        last_violence_run = 0.0
        completion_times: list[float] = []
        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            now = time.monotonic()
            if now - last_run < min_interval:
                continue  # throttle to configured inference FPS
            last_run = now

            violence_prediction: ViolencePrediction | None = None
            if self._violence_classifier is not None and now - last_violence_run >= 1.0:
                last_violence_run = now
                try:
                    violence_prediction = self._violence_classifier.predict(frame)
                except Exception:
                    logger.exception(
                        "Camera %s: CLIP violence classification failed", self.camera_id
                    )

            if self._detector is None:
                # No detector configured -- still serve the raw feed so the
                # dashboard's Live Monitoring page shows *something* useful,
                # clearly without any detection overlay.
                jpeg = encode_jpeg(frame)
                self._evaluate_rules(
                    [],
                    frame_width=frame.shape[1],
                    frame_height=frame.shape[0],
                    now=now,
                    snapshot=jpeg,
                    frame_bgr=frame,
                    violence_prediction=violence_prediction,
                )
                with self._lock:
                    self._latest_jpeg = jpeg
                    self._latest_tracks = []
                continue

            try:
                detections = self._detector.detect(frame, confidence_threshold=0.4)
            except DetectorUnavailableError as exc:
                logger.error("Camera %s: detector unavailable: %s", self.camera_id, exc)
                with self._lock:
                    self._health.last_error = f"Detector unavailable: {exc}"
                # Continue with empty tracks so the independent frame-level
                # violence classifier can still produce a review alert.
                detections = []

            tracks = self._tracker.update(detections)
            annotated = annotate_frame(frame, tracks)

            completion_now = time.monotonic()
            completion_times.append(completion_now)
            completion_times = [t for t in completion_times if completion_now - t <= 5.0]
            with self._lock:
                self._health.measured_inference_fps = (
                    len(completion_times) / 5.0 if len(completion_times) > 1 else 0.0
                )

            weapon_detections: list = []
            if self._weapon_detector is not None:
                try:
                    weapon_detections = self._weapon_detector.detect(
                        frame, confidence_threshold=0.4
                    )
                except DetectorUnavailableError as exc:
                    logger.error("Camera %s: weapon detector unavailable: %s", self.camera_id, exc)

            jpeg = encode_jpeg(annotated)

            self._evaluate_rules(
                tracks,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0],
                now=now,
                snapshot=jpeg,
                weapon_detections=weapon_detections,
                frame_bgr=frame,
                violence_prediction=violence_prediction,
            )

            with self._lock:
                self._latest_jpeg = jpeg
                self._latest_tracks = tracks

    def _evaluate_rules(
        self,
        tracks: list[Track],
        frame_width: int,
        frame_height: int,
        now: float,
        snapshot: bytes,
        weapon_detections: list | None = None,
        frame_bgr=None,
        violence_prediction: ViolencePrediction | None = None,
    ) -> None:
        """Runs every configured rule against this frame's tracks and
        forwards any trigger to the backend-provided callback. Errors here
        are logged, never allowed to crash the inference loop -- a broken
        rule or a DB hiccup in the callback must not take down live video."""
        if (
            not self._zone_rules
            and self._abandoned_object_rule is None
            and self._aggressive_motion_rule is None
            and self._weapon_confirmation_rule is None
            and self._violence_confirmation_rule is None
        ):
            return

        events: list[RuleTriggerEvent] = []
        occurred_at = datetime.now(UTC)

        for zone_rule in self._zone_rules:
            try:
                intrusions = zone_rule.evaluate(tracks, frame_width, frame_height, now)
            except Exception:
                logger.exception("Camera %s: zone rule evaluation failed", self.camera_id)
                continue
            for intrusion_ev in intrusions:
                events.append(
                    RuleTriggerEvent(
                        category="intrusion",
                        camera_id=self.camera_id,
                        track_ids=[intrusion_ev.track_id],
                        severity=intrusion_ev.severity,
                        occurred_at=occurred_at,
                        zone_id=intrusion_ev.zone_id,
                        zone_name=intrusion_ev.zone_name,
                        evidence={"dwell_seconds": round(intrusion_ev.dwell_seconds, 1)},
                    )
                )

        if self._abandoned_object_rule is not None:
            try:
                abandoned = self._abandoned_object_rule.evaluate(
                    tracks,
                    now,
                    frame_bgr=frame_bgr,
                    classifier=self._abandoned_object_classifier,
                )
            except Exception:
                logger.exception(
                    "Camera %s: abandoned-object rule evaluation failed", self.camera_id
                )
                abandoned = []
            for abandoned_ev in abandoned:
                events.append(
                    RuleTriggerEvent(
                        category="abandoned_object",
                        camera_id=self.camera_id,
                        track_ids=[abandoned_ev.track_id],
                        severity="medium",
                        occurred_at=occurred_at,
                        evidence={
                            "object_class": abandoned_ev.class_name,
                            "stationary_seconds": round(abandoned_ev.stationary_seconds, 1),
                            **(
                                {
                                    "classifier_label": abandoned_ev.classifier_label,
                                    "classifier_confidence": round(
                                        abandoned_ev.classifier_confidence, 4
                                    ),
                                }
                                if abandoned_ev.classifier_label is not None
                                and abandoned_ev.classifier_confidence is not None
                                else {}
                            ),
                        },
                    )
                )

        if self._aggressive_motion_rule is not None:
            try:
                motion_events = self._aggressive_motion_rule.evaluate(tracks, now)
            except Exception:
                logger.exception(
                    "Camera %s: aggressive-motion rule evaluation failed", self.camera_id
                )
                motion_events = []
            for motion_ev in motion_events:
                events.append(
                    RuleTriggerEvent(
                        category="aggressive_motion",
                        camera_id=self.camera_id,
                        track_ids=list(motion_ev.track_ids),
                        severity=motion_ev.severity,
                        occurred_at=occurred_at,
                        evidence={
                            "consecutive_frames": motion_ev.consecutive_frames,
                            "note": "Aggressive motion -- review required. Not a confirmed fight.",
                        },
                    )
                )

        if self._weapon_confirmation_rule is not None and weapon_detections:
            try:
                weapon_events = self._weapon_confirmation_rule.evaluate(weapon_detections, now)
            except Exception:
                logger.exception(
                    "Camera %s: weapon confirmation rule evaluation failed", self.camera_id
                )
                weapon_events = []
            for weapon_ev in weapon_events:
                events.append(
                    RuleTriggerEvent(
                        category="weapon",
                        camera_id=self.camera_id,
                        track_ids=[],
                        severity=weapon_ev.severity,
                        occurred_at=occurred_at,
                        evidence={
                            "weapon_class": weapon_ev.class_name,
                            "confidence": round(weapon_ev.confidence, 2),
                            "consecutive_frames": weapon_ev.consecutive_frames,
                            "note": "Possible weapon -- review required. Not a confirmed weapon.",
                        },
                    )
                )

        if self._violence_confirmation_rule is not None and violence_prediction is not None:
            try:
                violence_events = self._violence_confirmation_rule.evaluate(
                    violence_prediction, now
                )
            except Exception:
                logger.exception("Camera %s: violence confirmation rule failed", self.camera_id)
                violence_events = []
            for violence_ev in violence_events:
                events.append(
                    RuleTriggerEvent(
                        category="fight",
                        camera_id=self.camera_id,
                        track_ids=[],
                        severity=violence_ev.severity,
                        occurred_at=occurred_at,
                        evidence={
                            "prediction": violence_ev.label,
                            "similarity": round(violence_ev.similarity, 3),
                            "consecutive_frames": violence_ev.consecutive_frames,
                            "note": (
                                "Possible violence -- review required; model score is not "
                                "a probability."
                            ),
                        },
                        dedup_key=f"fight:{self.camera_id}:clip-violence",
                    )
                )

        if self._on_rule_triggered is None:
            return
        for event in events:
            try:
                self._on_rule_triggered(event, snapshot)
            except Exception:
                logger.exception("Camera %s: on_rule_triggered callback failed", self.camera_id)
