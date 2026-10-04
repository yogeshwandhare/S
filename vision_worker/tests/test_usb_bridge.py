"""USB routing regressions; runnable with unittest without extra test packages."""

import os
import unittest
from unittest.mock import patch

import cv2

from vision_worker.pipeline.source import (
    CameraConnectionError,
    FrameSource,
    FrameSourceConfig,
    SourceType,
)


class UsbBridgeTests(unittest.TestCase):
    def test_http_stream_uses_ffmpeg_with_timeouts(self):
        with patch("vision_worker.pipeline.source.cv2.VideoCapture") as capture:
            source = FrameSource(FrameSourceConfig(SourceType.HTTP, "http://phone:8080/video"))
            source.open()
            capture.assert_called_once_with(
                "http://phone:8080/video", cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
            )

    def test_native_usb_still_uses_device_index(self):
        with patch.dict(os.environ, {"USB_CAMERA_BRIDGE_URL": ""}), patch(
            "vision_worker.pipeline.source.cv2.VideoCapture"
        ) as capture:
            source = FrameSource(FrameSourceConfig(SourceType.USB, "0"))
            source.open()
            capture.assert_called_once_with(0, cv2.CAP_ANY)
            source.close()
            capture.return_value.release.assert_called_once()

    def test_bridge_uses_ffmpeg_and_bounded_timeouts(self):
        with patch.dict(os.environ, {"USB_CAMERA_BRIDGE_URL": "http://host:8765/private/"}), patch(
            "vision_worker.pipeline.source.cv2.VideoCapture"
        ) as capture:
            source = FrameSource(FrameSourceConfig(SourceType.USB, "2"))
            source.open()
            capture.assert_called_once_with(
                "http://host:8765/private/2.mjpg", cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
            )

    def test_failed_bridge_does_not_expose_token(self):
        with patch.dict(os.environ, {"USB_CAMERA_BRIDGE_URL": "http://host/private-token"}), patch(
            "vision_worker.pipeline.source.cv2.VideoCapture"
        ) as capture:
            capture.return_value.isOpened.return_value = False
            source = FrameSource(FrameSourceConfig(SourceType.USB, "0"))
            with self.assertRaisesRegex(CameraConnectionError, "Could not open source: 0"):
                source.open()
            self.assertNotIn("private-token", source.last_error)
            capture.return_value.release.assert_called_once()

    def test_bridge_does_not_override_rtsp(self):
        with patch.dict(os.environ, {"USB_CAMERA_BRIDGE_URL": "http://host/private"}):
            source = FrameSource(FrameSourceConfig(SourceType.RTSP, "rtsp://camera/live"))
            self.assertEqual(source._resolve_uri(), "rtsp://camera/live")

    def test_bridge_rejects_invalid_index(self):
        with patch.dict(os.environ, {"USB_CAMERA_BRIDGE_URL": "http://host/private"}):
            source = FrameSource(FrameSourceConfig(SourceType.USB, "../other"))
            with self.assertRaises(CameraConnectionError):
                source.open()


if __name__ == "__main__":
    unittest.main()
