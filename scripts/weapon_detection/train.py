#!/usr/bin/env python3
"""
Fine-tune a weapon detector on the prepared Sohas dataset.

Uses `ultralytics` for training -- the same AGPL-3.0-licensed package
already used as the optional YOLO object-detection adapter (see
docs/MODEL_REGISTRY.md). Because training uses this package, the resulting
weapon-detection checkpoint is treated the same way as that adapter:
disabled by default, and requires the same explicit AGPL-3.0
acknowledgement to enable (see scripts/download_models.py's
`--enable-yolo-agpl` flag, which also governs the weapon detector).

Usage:
    python scripts/weapon_detection/train.py \
        --dataset data/weapon_detection/dataset.yaml \
        --epochs 50 \
        --output-dir models/weapon_detector

For a quick correctness check of the pipeline itself (not a usable model),
pass a small --epochs value. Real deployment-quality training needs many
more epochs and, ideally, the full upstream dataset (this repository ships
against a subset -- see docs/MODEL_REGISTRY.md for exactly why).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path, help="Path to dataset.yaml")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument(
        "--base-checkpoint",
        default="yolo11n.pt",
        help="Pretrained checkpoint to fine-tune from (downloaded automatically).",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "The 'ultralytics' package is required to train the weapon detector.\n"
            "From backend/, run: uv sync --extra yolo",
            file=sys.stderr,
        )
        return 1

    if not args.dataset.exists():
        print(f"Dataset config not found: {args.dataset}", file=sys.stderr)
        print("Run scripts/weapon_detection/prepare_dataset.py first.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fine-tuning {args.base_checkpoint} on {args.dataset} for {args.epochs} epochs...")
    model = YOLO(args.base_checkpoint)
    results = model.train(
        data=str(args.dataset.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(args.output_dir),
        name="train",
        exist_ok=True,
        device="cpu",
        verbose=True,
    )

    best_checkpoint = Path(results.save_dir) / "weights" / "best.pt"
    print(f"\nTraining complete. Best checkpoint: {best_checkpoint}")

    metadata = {
        "base_checkpoint": args.base_checkpoint,
        "epochs": args.epochs,
        "dataset": str(args.dataset.resolve()),
        "best_checkpoint": str(best_checkpoint),
    }
    metadata_path = args.output_dir / "training_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"Wrote {metadata_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
