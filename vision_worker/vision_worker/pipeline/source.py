"""Camera frame source.

A thin, uniform wrapper around `cv2.VideoCapture` that works the same way
whether the underlying source is an RTSP stream, a local video file, or a
USB webcam. Handles reconnect-with-backoff for network sources and reports
health status the backend can surface to the dashboard.

This module does NOT decide *when* to read frames or what to do with them
-- that's `CameraWorker` in `pipeline/worker.py`. Keeping the two separate
means this class can be unit-tested (open/read/health/close) without
needing a running asyncio event loop.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SourceType(StrEnum):
    RTSP = "rtsp"
    FILE = "file"
    USB = "usb"


@dataclass
class FrameSourceConfig:
    source_type: SourceType
    # RTSP: an rtsp:// URL. FILE: a filesystem path. USB: a device index
    # as a string, e.g. "0".
    uri: str
    # Force RTSP-over-TCP (more reliable than the UDP default on lossy
    # networks, at some added latency) -- see the project brief's
    # requirement to support RTSP-over-TCP explicitly.
    force_tcp: bool = True


class CameraConnectionError(RuntimeError):
    """Raised when a source cannot be opened at all (bad URI, unreachable
    host, missing device). Distinct from a transient read failure, which
    the caller retries instead of raising."""


class FrameSource:
    """Opens and reads from exactly one camera/file/USB source.

    Not thread-safe -- each `CameraWorker` owns exactly one `FrameSource`
    instance and calls it from a single thread, which matches how
    `cv2.VideoCapture` is meant to be used.
    """

    def __init__(self, config: FrameSourceConfig) -> None:
        self.config = config
        self._cap: cv2.VideoCapture | None = None
        self.last_error: str | None = None

    def open(self) -> None:
        uri = self._resolve_uri()
        capture_backend = (
            cv2.CAP_FFMPEG if self.config.source_type != SourceType.USB else cv2.CAP_ANY
        )

        cap = cv2.VideoCapture(uri, capture_backend)
        if not cap.isOpened():
            cap.release()
            self.last_error = f"Could not open source: {self._safe_uri_for_logging()}"
            raise CameraConnectionError(self.last_error)

        self._cap = cap
        self.last_error = None

    def _resolve_uri(self) -> str | int:
        if self.config.source_type == SourceType.USB:
            try:
                return int(self.config.uri)
            except ValueError as exc:
                raise CameraConnectionError(
                    f"USB source URI must be a device index, got {self.config.uri!r}"
                ) from exc

        if self.config.source_type == SourceType.RTSP and self.config.force_tcp:
            # OpenCV/FFmpeg reads RTSP transport preference from this
            # environment variable at capture-open time.
            import os

            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

        return self.config.uri

    def _safe_uri_for_logging(self) -> str:
        """Never leak embedded RTSP credentials (rtsp://user:pass@host/...)
        into logs or health-check error messages surfaced to the frontend."""
        uri = self.config.uri
        if "@" in uri and "://" in uri:
            scheme, rest = uri.split("://", 1)
            _, _, host_part = rest.partition("@")
            return f"{scheme}://***:***@{host_part}"
        return uri

    def read(self) -> np.ndarray | None:
        """Read one frame. Returns None on a transient read failure
        (caller should retry/reconnect) rather than raising, since a single
        dropped frame from a flaky RTSP stream is normal, not exceptional."""
        if self._cap is None:
            raise RuntimeError("FrameSource.read() called before open()")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return frame

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def compute_backoff_seconds(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with a cap, for reconnect attempts.
    `attempt` is 0-indexed (0 = first retry)."""
    return min(cap, base * (2**attempt))


def wait_with_backoff(attempt: int, sleep_fn=time.sleep) -> None:
    sleep_fn(compute_backoff_seconds(attempt))
