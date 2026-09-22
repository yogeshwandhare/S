from __future__ import annotations

import os

import pytest
from vision_worker.pipeline.source import (
    CameraConnectionError,
    FrameSource,
    FrameSourceConfig,
    SourceType,
    compute_backoff_seconds,
)

SAMPLE_VIDEO = os.path.join(
    os.path.dirname(__file__), "..", "..", "sample_data", "synthetic_pipeline_test.mp4"
)
SAMPLE_VIDEO = os.path.normpath(SAMPLE_VIDEO)


@pytest.mark.skipif(not os.path.exists(SAMPLE_VIDEO), reason="sample video fixture not present")
def test_file_source_opens_and_reads_frames():
    source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=SAMPLE_VIDEO))
    source.open()
    assert source.is_open
    frame = source.read()
    assert frame is not None
    assert frame.ndim == 3
    source.close()
    assert not source.is_open


def test_missing_file_raises_connection_error():
    source = FrameSource(
        FrameSourceConfig(source_type=SourceType.FILE, uri="/nonexistent/path/video.mp4")
    )
    with pytest.raises(CameraConnectionError):
        source.open()


def test_invalid_usb_index_raises_connection_error():
    source = FrameSource(FrameSourceConfig(source_type=SourceType.USB, uri="not-a-number"))
    with pytest.raises(CameraConnectionError):
        source.open()


def test_read_before_open_raises():
    source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=SAMPLE_VIDEO))
    with pytest.raises(RuntimeError):
        source.read()


def test_credentials_scrubbed_from_logged_uri():
    source = FrameSource(
        FrameSourceConfig(
            source_type=SourceType.RTSP,
            uri="rtsp://admin:supersecret@192.168.1.50:554/stream1",
        )
    )
    safe = source._safe_uri_for_logging()
    assert "supersecret" not in safe
    assert "admin" not in safe
    assert "192.168.1.50" in safe


def test_backoff_grows_exponentially_and_is_capped():
    assert compute_backoff_seconds(0) == 1.0
    assert compute_backoff_seconds(1) == 2.0
    assert compute_backoff_seconds(2) == 4.0
    assert compute_backoff_seconds(10) == 30.0  # capped
