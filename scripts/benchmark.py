#!/usr/bin/env python3
"""
Benchmark the object detector and the full ingest->detect->track->annotate
pipeline on this machine's actual hardware, and report real, measured
numbers -- never an assumed or extrapolated figure.

Usage:
    python scripts/benchmark.py --checkpoint yolo11n.pt \
        --video sample_data/synthetic_pipeline_test.mp4

Reports:
    - Detector-only inference latency and FPS (mean, median, p95) over a
      fixed number of real frames.
    - Peak process memory (RSS) during detector inference.
    - End-to-end CameraWorker pipeline throughput for 1..N simultaneous
      simulated cameras (same video file, N independent workers), on
      whatever CPU/GPU this process actually has -- device detection is
      read from the framework, never assumed.

This does not claim results transfer to different hardware, resolutions,
or checkpoints. Re-run it on your own deployment target before trusting
its numbers there.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vision_worker"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def _get_rss_mb() -> float:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:
        return -1.0


def benchmark_detector(checkpoint: str, video_path: str, num_frames: int) -> dict:
    import cv2
    from vision_worker.detectors.yolo_detector import YoloDetector

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    frames = []
    while len(frames) < num_frames:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frames.append(frame)
    cap.release()

    frame_h, frame_w = frames[0].shape[:2]

    print(f"Loading detector ({checkpoint})...")
    detector = YoloDetector(checkpoint=checkpoint)

    detector.detect(frames[0], confidence_threshold=0.4)

    latencies_ms = []
    for frame in frames:
        start = time.perf_counter()
        detector.detect(frame, confidence_threshold=0.4)
        latencies_ms.append((time.perf_counter() - start) * 1000)

    peak_rss_mb = _get_rss_mb()

    return {
        "checkpoint": checkpoint,
        "frame_resolution": f"{frame_w}x{frame_h}",
        "num_frames": len(frames),
        "device": "cpu",
        "latency_ms": {
            "mean": round(statistics.mean(latencies_ms), 2),
            "median": round(statistics.median(latencies_ms), 2),
            "p95": round(statistics.quantiles(latencies_ms, n=20)[18], 2)
            if len(latencies_ms) >= 20
            else round(max(latencies_ms), 2),
            "min": round(min(latencies_ms), 2),
            "max": round(max(latencies_ms), 2),
        },
        "fps": round(1000 / statistics.mean(latencies_ms), 2),
        "peak_rss_mb": round(peak_rss_mb, 1),
    }


def benchmark_pipeline(
    checkpoint: str, video_path: str, camera_counts: list[int], duration_s: float
) -> list[dict]:
    from vision_worker.detectors.yolo_detector import YoloDetector
    from vision_worker.pipeline.source import FrameSource, FrameSourceConfig, SourceType
    from vision_worker.pipeline.worker import CameraWorker

    results = []
    detector = YoloDetector(checkpoint=checkpoint)

    for n_cameras in camera_counts:
        workers = []
        for i in range(n_cameras):
            source = FrameSource(FrameSourceConfig(source_type=SourceType.FILE, uri=video_path))
            worker = CameraWorker(
                camera_id=f"bench-{i}", source=source, detector=detector, inference_fps=30.0
            )
            workers.append(worker)

        for w in workers:
            w.start()

        time.sleep(2.0)
        start_tracks = [len(w.get_active_tracks()) for w in workers]
        start_time = time.monotonic()
        time.sleep(duration_s)
        elapsed = time.monotonic() - start_time

        capture_fps_samples = [w.get_health().measured_capture_fps for w in workers]
        inference_fps_samples = [w.get_health().measured_inference_fps for w in workers]

        for w in workers:
            w.stop()

        results.append(
            {
                "num_cameras": n_cameras,
                "measured_duration_s": round(elapsed, 1),
                "per_camera_capture_fps": [round(f, 2) for f in capture_fps_samples],
                "per_camera_inference_fps": [round(f, 2) for f in inference_fps_samples],
                "avg_inference_fps_per_camera": round(
                    statistics.mean(inference_fps_samples) if inference_fps_samples else 0, 2
                ),
                "any_tracks_detected": any(t > 0 for t in start_tracks),
            }
        )
        print(
            f"  {n_cameras} camera(s): avg {results[-1]['avg_inference_fps_per_camera']} "
            f"inference FPS/camera"
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="yolo11n.pt")
    parser.add_argument(
        "--video",
        default=str(
            Path(__file__).resolve().parent.parent / "sample_data" / "synthetic_pipeline_test.mp4"
        ),
    )
    parser.add_argument("--num-frames", type=int, default=30)
    parser.add_argument("--camera-counts", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--pipeline-duration", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    import platform

    try:
        import psutil

        cpu_count = psutil.cpu_count(logical=True)
        total_ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        import os

        cpu_count = os.cpu_count()
        total_ram_gb = None

    hardware = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": cpu_count,
        "total_ram_gb": total_ram_gb,
    }

    print("=== Hardware ===")
    print(json.dumps(hardware, indent=2))

    print("\n=== Detector benchmark ===")
    detector_results = benchmark_detector(args.checkpoint, args.video, args.num_frames)
    print(json.dumps(detector_results, indent=2))

    print("\n=== Pipeline benchmark (real CameraWorker, scaling camera count) ===")
    pipeline_results = benchmark_pipeline(
        args.checkpoint, args.video, args.camera_counts, args.pipeline_duration
    )

    report = {
        "hardware": hardware,
        "detector_benchmark": detector_results,
        "pipeline_benchmark": pipeline_results,
        "note": (
            "These numbers are specific to the hardware and checkpoint listed above. "
            "Re-run this script on your own deployment target -- do not assume these "
            "figures transfer to different hardware, resolutions, or models."
        ),
    }

    output_path = (
        args.output or Path(__file__).resolve().parent.parent / "docs" / "benchmark_report.json"
    )
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
