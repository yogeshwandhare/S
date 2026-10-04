"""Share selected Windows cameras with Docker; discover devices without opening them.

Setup: py -3 -m pip install --target .usb-camera/packages -r scripts/usb_camera_requirements.txt
Run:   py -3 scripts/usb_camera_bridge.py --configure-docker
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".usb-camera" / "packages"))


class BridgeServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def enumerate_devices():
    from cv2_enumerate_cameras import enumerate_cameras

    if os.name != "nt":
        return enumerate_cameras(cv2.CAP_ANY)
    return merge_windows_devices(
        list(enumerate_cameras(cv2.CAP_MSMF)) + list(enumerate_cameras(cv2.CAP_DSHOW))
    )


def merge_windows_devices(devices):
    """Match the device instance across different Windows interface-class GUIDs."""
    grouped = {}
    for info in devices:
        if not info.path:
            continue
        identity = str(info.path).split("#{", 1)[0].casefold()
        if identity not in grouped:
            grouped[identity] = SimpleNamespace(
                index=info.index, backend=info.backend, name=info.name, path=info.path,
                identity=identity, capture_options=[], legacy_paths=[],
            )
        grouped[identity].capture_options.append((info.index, info.backend))
        grouped[identity].legacy_paths.append(str(info.path))
    return list(grouped.values())


class DeviceRegistry:
    """Persist logical device IDs so an unplug cannot silently select another camera."""

    def __init__(self, path: Path, enumerate_fn=enumerate_devices):
        self.path = path
        self.enumerate_fn = enumerate_fn
        self.lock = threading.Lock()
        self.ids = json.loads(path.read_text()) if path.exists() else {}

    def discover(self) -> dict:
        with self.lock:
            devices = {}
            changed = False
            for info in self.enumerate_fn():
                if not info.path:
                    continue
                identity = hashlib.sha256(
                    getattr(info, "identity", str(info.path)).encode()
                ).hexdigest()
                if identity not in self.ids:
                    used = set(self.ids.values())
                    preferred = int(info.index)
                    legacy = [
                        self.ids[old] for path in getattr(info, "legacy_paths", [])
                        if (old := hashlib.sha256(path.encode()).hexdigest()) in self.ids
                    ]
                    self.ids[identity] = (
                        legacy[0] if legacy else preferred if preferred not in used else max(used) + 1
                    )
                    changed = True
                devices[self.ids[identity]] = info
            if changed:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(self.ids), encoding="utf-8")
                temporary.replace(self.path)
            return devices


class CameraFeed:
    """One capture handle shared by the worker and connection-test clients."""

    def __init__(self, info):
        self.info = info
        self.condition = threading.Condition()
        self.stopped = threading.Event()
        self.users = 0
        self.latest = None
        self.sequence = 0
        self.thread = threading.Thread(target=self.capture, daemon=True)

    def capture(self):
        cap = None
        try:
            options = getattr(self.info, "capture_options", [(self.info.index, self.info.backend)])
            frame = None
            for index, backend in options:
                candidate = cv2.VideoCapture(index, backend)
                candidate.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                candidate.set(cv2.CAP_PROP_FPS, 15)
                ok, frame = candidate.read()
                if ok and frame is not None:
                    cap = candidate
                    break
                candidate.release()
            if cap is None:
                return
            while not self.stopped.is_set():
                with self.condition:
                    if self.users == 0:
                        self.stopped.set()
                        break
                started = time.monotonic()
                encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if encoded:
                    with self.condition:
                        self.latest = jpeg.tobytes()
                        self.sequence += 1
                        self.condition.notify_all()
                self.stopped.wait(max(0, 1 / 15 - (time.monotonic() - started)))
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
        finally:
            if cap is not None:
                cap.release()
            with self.condition:
                self.latest = None
                self.stopped.set()
                self.condition.notify_all()

    def next_frame(self, previous):
        with self.condition:
            ready = self.condition.wait_for(
                lambda: self.sequence != previous or self.stopped.is_set(), timeout=4
            )
            if not ready or self.stopped.is_set():
                return None, previous
            return self.latest, self.sequence


class CameraPool:
    def __init__(self, registry):
        self.registry = registry
        self.lock = threading.Lock()
        self.feeds = {}

    def acquire(self, device_id):
        info = self.registry.discover().get(device_id)
        if info is None:
            return None
        with self.lock:
            feed = self.feeds.get(device_id)
            if feed is not None and feed.stopped.is_set():
                feed.thread.join(timeout=1)
                if feed.thread.is_alive():
                    return None
                feed = None
            if feed is None:
                feed = CameraFeed(info)
                feed.users = 1
                self.feeds[device_id] = feed
                feed.thread.start()
            else:
                with feed.condition:
                    if feed.stopped.is_set():
                        return None
                    feed.users += 1
            return feed

    def release(self, feed):
        with feed.condition:
            feed.users -= 1

    def close(self):
        with self.lock:
            for feed in self.feeds.values():
                feed.stopped.set()
            for feed in self.feeds.values():
                feed.thread.join(timeout=5)


def make_handler(token, registry, pool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log the token in request paths.

        def do_GET(self):
            parts = self.path.split("/")
            if len(parts) != 3 or not secrets.compare_digest(parts[1].encode(), token.encode()):
                self.send_error(404)
                return
            route = parts[2]
            if route == "devices":
                try:
                    devices = [
                        {"index": index, "name": info.name}
                        for index, info in registry.discover().items()
                    ]
                except Exception:
                    self.send_error(503, "Windows camera discovery failed")
                    return
                payload = json.dumps(devices).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return
            if not route.endswith(".mjpg") or not route[:-5].isdigit():
                self.send_error(404)
                return
            try:
                feed = pool.acquire(int(route[:-5]))
            except Exception:
                self.send_error(503, "Camera discovery failed")
                return
            if feed is None:
                self.send_error(503, "Selected camera is disconnected")
                return
            try:
                jpeg, sequence = feed.next_frame(0)
                if jpeg is None:
                    self.send_error(503, "Cannot read camera; check camera permissions and other apps")
                    return
                self.connection.settimeout(5)
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while jpeg is not None:
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
                    )
                    self.wfile.flush()
                    jpeg, sequence = feed.next_frame(sequence)
            except OSError:
                pass
            finally:
                pool.release(feed)

    return Handler


def configure_docker(token, port):
    env_file = ROOT / ".env"
    lines = env_file.read_text(encoding="utf-8-sig").splitlines() if env_file.exists() else []
    lines = [line for line in lines if not line.strip().startswith("USB_CAMERA_BRIDGE_URL=")]
    lines.append(f"USB_CAMERA_BRIDGE_URL=http://host.docker.internal:{port}/{token}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--configure-docker", action="store_true")
    parser.add_argument("--list", action="store_true", help="List devices without opening a camera")
    args = parser.parse_args()
    state = ROOT / ".usb-camera"
    state.mkdir(exist_ok=True)
    registry = DeviceRegistry(state / "devices.json")
    try:
        devices = registry.discover()
    except ImportError:
        raise SystemExit("Install scripts/usb_camera_requirements.txt as described in this script.")
    for index, info in devices.items():
        print(f"Device {index}: {info.name}", flush=True)
    if args.list:
        return
    token_path = state / "token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise SystemExit("Invalid bridge token; remove .usb-camera/token to regenerate it.")
    pool = CameraPool(registry)
    try:
        server = BridgeServer((args.bind, args.port), make_handler(token, registry, pool))
    except OSError:
        raise SystemExit(f"Port {args.port} is in use. Stop the previous bridge before restarting.")
    if args.configure_docker:
        configure_docker(token, args.port)
    print(f"Camera bridge ready on {args.bind}:{args.port}. Select a camera in SmartVision.", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        pool.close()
        server.server_close()


if __name__ == "__main__":
    main()
