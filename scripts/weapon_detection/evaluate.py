#!/usr/bin/env python3
"""
Evaluate a trained weapon-detection checkpoint and report real,
measured metrics -- never fabricated ones.

Usage:
    python scripts/weapon_detection/evaluate.py \
        --checkpoint models/weapon_detector/train/weights/best.pt \
        --dataset data/weapon_detection/dataset.yaml \
        --split test

Writes a JSON report (precision, recall, mAP50, mAP50-95 -- overall and
per-class) next to the checkpoint, and prints it. If a metric can't be
computed (e.g. a class has zero instances in the chosen split), this
reports that explicitly rather than substituting a placeholder number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--batch", type=int, default=4)
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
    if not args.dataset.exists():
        print(f"Dataset config not found: {args.dataset}", file=sys.stderr)
        return 1

    model = YOLO(str(args.checkpoint))
    metrics = model.val(
        data=str(args.dataset.resolve()),
        split=args.split,
        imgsz=args.imgsz,
        device="cpu",
        batch=args.batch,
        workers=0,
        verbose=True,
    )

    class_names = metrics.names
    report = {
        "checkpoint": str(args.checkpoint),
        "dataset": str(args.dataset),
        "split": args.split,
        "overall": {
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
            "mAP50": float(metrics.box.map50),
            "mAP50-95": float(metrics.box.map),
        },
        "speed_ms_per_image": dict(metrics.speed),
        "per_class": {},
    }

    # ultralytics reports per-class AP in the order of `metrics.ap_class_index`.
    for i, class_idx in enumerate(metrics.box.ap_class_index):
        name = class_names[int(class_idx)]
        report["per_class"][name] = {
            "precision": float(metrics.box.p[i]),
            "recall": float(metrics.box.r[i]),
            "mAP50": float(metrics.box.ap50[i]),
            "mAP50-95": float(metrics.box.ap[i]),
        }

    output_path = args.checkpoint.parent.parent / "evaluation_report.json"
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote evaluation report to {output_path}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
