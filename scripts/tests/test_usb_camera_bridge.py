import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from scripts.usb_camera_bridge import (
    BridgeServer, CameraFeed, CameraPool, DeviceRegistry, make_handler, merge_windows_devices,
)


def camera(index, path, name="USB Camera"):
    return SimpleNamespace(index=index, path=path, name=name, backend=700)


class RegistryTests(unittest.TestCase):
    def test_windows_capture_methods_are_grouped_by_device_identity(self):
        media = camera(2, "device#{media-guid}", "External")
        media.backend = 1400
        direct = camera(1, "device#{direct-guid}", "External")
        grouped = merge_windows_devices([media, direct, camera(0, "other#{guid}")])
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0].capture_options, [(2, 1400), (1, 700)])

    def test_capture_method_change_keeps_legacy_device_id(self):
        self.devices = [camera(1, "external#{direct}")]
        self.registry.discover()
        media = camera(0, "external#{media}")
        media.backend = 1400
        self.devices = merge_windows_devices([media, self.devices[0]])
        found = self.registry.discover()
        self.assertEqual(list(found), [1])
        self.assertEqual(found[1].index, 0)

    def test_capture_falls_back_only_to_same_devices_other_method(self):
        import numpy as np
        info = camera(2, "external")
        info.capture_options = [(2, 1400), (1, 700)]
        feed = CameraFeed(info)
        feed.users = 1
        failed = Mock()
        failed.read.return_value = (False, None)
        working = Mock()
        working.read.side_effect = [(True, np.zeros((4, 4, 3), dtype=np.uint8)), (False, None)]
        with patch("scripts.usb_camera_bridge.cv2.VideoCapture", side_effect=[failed, working]) as capture:
            feed.capture()
            self.assertEqual([call.args for call in capture.call_args_list], [(2, 1400), (1, 700)])
        failed.release.assert_called_once()
        working.release.assert_called_once()
        self.assertEqual(feed.sequence, 1)

    def test_duplicate_bridge_cannot_bind_same_port(self):
        handler = make_handler("secret", Mock(), Mock())
        server = BridgeServer(("127.0.0.1", 0), handler)
        try:
            with self.assertRaises(OSError):
                BridgeServer(server.server_address, handler)
        finally:
            server.server_close()

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.devices = [camera(0, "laptop", "Laptop"), camera(1, "external")]
        self.path = Path(self.directory.name) / "devices.json"
        self.registry = DeviceRegistry(self.path, lambda: self.devices)

    def test_reconnect_with_changed_os_index_preserves_identity(self):
        self.assertEqual(self.registry.discover()[1].path, "external")
        self.devices = [camera(0, "external")]
        found = self.registry.discover()
        self.assertNotIn(0, found)
        self.assertEqual(found[1].index, 0)
        restarted = DeviceRegistry(self.path, lambda: self.devices)
        self.assertEqual(restarted.discover()[1].path, "external")

    def test_replacement_camera_does_not_reuse_missing_device_id(self):
        self.registry.discover()
        self.devices = [camera(0, "laptop"), camera(1, "different-external")]
        found = self.registry.discover()
        self.assertNotIn(1, found)
        self.assertEqual(found[2].path, "different-external")

    def test_unplugged_camera_never_falls_back_to_laptop(self):
        self.registry.discover()
        self.devices = [camera(0, "laptop")]
        with patch("scripts.usb_camera_bridge.cv2.VideoCapture") as capture:
            self.assertIsNone(CameraPool(self.registry).acquire(1))
            capture.assert_not_called()

    def test_newly_plugged_camera_is_discovered_without_restart(self):
        self.devices = []
        self.assertEqual(self.registry.discover(), {})
        self.devices.append(camera(0, "new"))
        self.assertEqual(self.registry.discover()[0].path, "new")

    def test_http_discovery_does_not_open_camera_and_requires_token(self):
        pool = Mock()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("secret", self.registry, pool))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/wrong/devices")
            self.assertEqual(error.exception.code, 404)
            with urlopen(base + "/secret/devices") as response:
                devices = json.load(response)
            self.assertEqual(devices, [{"index": 0, "name": "Laptop"}, {"index": 1, "name": "USB Camera"}])
            pool.acquire.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failed_capture_releases_device_and_clears_frame(self):
        feed = CameraFeed(camera(1, "external"))
        feed.users = 1
        feed.latest = b"old frame"
        with patch("scripts.usb_camera_bridge.cv2.VideoCapture") as capture:
            capture.return_value.read.return_value = (False, None)
            feed.capture()
            capture.return_value.release.assert_called_once()
        self.assertTrue(feed.stopped.is_set())
        self.assertEqual(feed.next_frame(0), (None, 0))


if __name__ == "__main__":
    unittest.main()
