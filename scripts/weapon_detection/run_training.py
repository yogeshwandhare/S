"""Run download, CPU fine-tuning, held-out evaluation and ONNX export.

Artifacts and logs persist under --work-dir. This does not enable the model;
review evaluation_report.json and validate inference before registration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    status_path = root / "status.json"
    def status(stage: str, **extra: object) -> None:
        status_path.write_text(json.dumps({"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}, indent=2))
    os.environ.update(OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", YOLO_CONFIG_DIR=str(root / "ultralytics"))
    dataset = root / "sohas" / "dataset.yaml"
    output = root / "weapon_detector"
    checkpoint = output / "train" / "weights" / "best.pt"
    steps = [
        ("download", ["download_dataset.py", "--output-dir", str(root / "sohas")]),
        ("training", ["train.py", "--dataset", str(dataset), "--output-dir", str(output), "--epochs", str(args.epochs), "--imgsz", "320", "--batch", "4", "--threads", "4", "--patience", "8"] + (["--resume", str(args.resume)] if args.resume else [])),
        ("evaluation", ["evaluate.py", "--dataset", str(dataset), "--checkpoint", str(checkpoint), "--split", "test"]),
        ("export", ["export_onnx.py", "--checkpoint", str(checkpoint)]),
    ]
    for stage, command in steps:
        status(stage, epochs_requested=args.epochs)
        with (root / f"{stage}.log").open("a", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, "-u", str(scripts / command[0]), *command[1:]], stdout=log, stderr=subprocess.STDOUT, cwd=root)
        if result.returncode:
            status("failed", failed_stage=stage, exit_code=result.returncode, log=str(root / f"{stage}.log"))
            return result.returncode
    status("complete_pending_review", checkpoint=str(checkpoint), onnx=str(checkpoint.with_suffix(".onnx")), evaluation=str(output / "train" / "evaluation_report.json"), enabled=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
