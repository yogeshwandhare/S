#!/usr/bin/env python3
"""
Export a trained weapon-detection checkpoint to ONNX, for inference via
ONNX Runtime (this project's optimized-inference stack, per the brief).

Usage:
    python scripts/weapon_detection/export_onnx.py \
        --checkpoint models/weapon_detector/train/weights/best.pt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--imgsz", type=int, default=320)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "The 'ultralytics' package is required. From backend/: uv sync --extra yolo",
            file=sys.stderr,
        )
        return 1

    if not args.checkpoint.exists():
        print(f"Checkpoint not found: {args.checkpoint}", file=sys.stderr)
        return 1

    model = YOLO(str(args.checkpoint))
    onnx_path = model.export(
        format="onnx", imgsz=args.imgsz, simplify=False, opset=17,
        dynamic=False, nms=False, batch=1,
    )
    print(f"\nExported ONNX model: {onnx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
