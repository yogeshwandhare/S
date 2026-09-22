from __future__ import annotations

import os
import time

import pytest
from vision_worker.pipeline.source import FrameSource, FrameSourceConfig, SourceType
from vision_worker.pipeline.worker import CameraWorker

SAMPLE_VIDEO = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "sample_data",
        "synthetic_pipeline_test.mp4",
    )
)


def _wait_until(predicate, timeout: float = 8.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.mark.skipif(not os.path.exists(SAMPLE_VIDEO), reason="sample video fixture not present")
def test_worker_with_no_detector_serves_raw_annotated_free_feed():
    """Without a configured detector, the worker should still serve JPEG
    frames (no detection overlay) rather than failing outright."""
    source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=SAMPLE_VIDEO))
    worker = CameraWorker(camera_id="cam-test-1", source=source, detector=None, inference_fps=10.0)
    worker.start()
    try:
        assert _wait_until(lambda: worker.get_latest_jpeg() is not None)
        jpeg = worker.get_latest_jpeg()
        assert jpeg is not None
        assert jpeg[:2] == b"\xff\xd8"

        health = worker.get_health()
        assert health.connected is True
        assert health.last_frame_at is not None
    finally:
        worker.stop()


def test_worker_reports_connection_error_for_missing_source():
    source = FrameSource(
        FrameSourceConfig(source_type=SourceType.FILE, uri="/nonexistent/video.mp4")
    )
    worker = CameraWorker(camera_id="cam-test-2", source=source, detector=None)
    worker.start()
    try:
        assert _wait_until(lambda: worker.get_health().last_error is not None, timeout=3.0)
        health = worker.get_health()
        assert health.connected is False
        assert health.last_error is not None
    finally:
        worker.stop()


def test_worker_stop_is_clean_and_joins_threads():
    source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=SAMPLE_VIDEO))
    worker = CameraWorker(camera_id="cam-test-3", source=source, detector=None, inference_fps=10.0)
    worker.start()
    _wait_until(lambda: worker.get_latest_jpeg() is not None)
    worker.stop(timeout=3.0)
    assert not worker._capture_thread.is_alive()
    assert not worker._inference_thread.is_alive()


@pytest.mark.skipif(not os.path.exists(SAMPLE_VIDEO), reason="sample video fixture not present")
@pytest.mark.slow
def test_worker_full_pipeline_with_real_detector_produces_real_tracks():
    """End-to-end: real file ingest -> real YOLO detection -> real tracking
    -> annotated JPEG output. Requires the yolo11n.pt checkpoint to already
    be cached (downloaded once during earlier manual testing in this repo's
    dev environment)."""
    from vision_worker.detectors.yolo_detector import YoloDetector

    try:
        detector = YoloDetector(checkpoint="yolo11n.pt")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"YOLO checkpoint not available in this environment: {exc}")

    source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=SAMPLE_VIDEO))
    worker = CameraWorker(
        camera_id="cam-test-4", source=source, detector=detector, inference_fps=10.0
    )
    worker.start()
    try:
        assert _wait_until(lambda: len(worker.get_active_tracks()) > 0, timeout=30.0)
        tracks = worker.get_active_tracks()
        assert len(tracks) >= 1
        # The sample video is a static real photo containing a bus + 4 people.
        class_names = {t.class_name for t in tracks}
        assert "person" in class_names or "bus" in class_names
        # measured_inference_fps needs at least two completed cycles within
        # its 5s window before it reports a rate (same pattern as
        # measured_capture_fps) -- wait for that explicitly rather than
        # checking immediately after the first track appears.
        assert _wait_until(lambda: worker.get_health().measured_inference_fps > 0, timeout=10.0)
    finally:
        worker.stop()
