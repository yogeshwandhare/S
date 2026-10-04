#!/usr/bin/env python3
"""
Download and register AI model checkpoints.

Usage:
    # Attempt to download and enable the default detector (RF-DETR Nano,
    # Apache-2.0). This is always attempted, never skipped.
    python scripts/download_models.py

    # Additionally offer the opt-in AGPL-3.0 YOLO adapter. Requires
    # explicit, separate acknowledgement of the AGPL-3.0 obligations --
    # see the confirmation prompt this prints before doing anything.
    python scripts/download_models.py --enable-yolo-agpl

This script is intentionally the ONLY way a model gets marked `enabled` in
the registry (there is no HTTP endpoint for it) -- enabling a detector,
especially one with copyleft licensing obligations, should be a deliberate
action taken by whoever operates the deployment, not something a web
request can flip.

What this does NOT do: it never fabricates success. If a checkpoint can't
be downloaded (network restrictions, changed URLs, etc.), the registry
entry is left with `is_available=False` and the reason is printed --
camera feeds then run with no detection overlay until the operator
resolves it, rather than silently pretending a model is active.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
backend_root = project_root / "backend"
if not (backend_root / "app").is_dir():
    backend_root = project_root  # Docker places the backend directly in /app.
sys.path.insert(0, str(backend_root))

import os  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.enums import ModelTask  # noqa: E402
from app.models.model_config import ModelConfig  # noqa: E402


def _upsert(
    db, *, task: ModelTask, name: str, license_: str, checkpoint_source: str
) -> ModelConfig:
    existing = db.scalar(select(ModelConfig).where(ModelConfig.name == name))
    if existing is not None:
        return existing
    config = ModelConfig(
        task=task,
        name=name,
        checkpoint_source=checkpoint_source,
        license=license_,
        is_available=False,
        enabled=False,
    )
    db.add(config)
    db.flush()
    return config


def _try_download_rfdetr_nano(db) -> None:
    print("\n=== RF-DETR Nano (Apache-2.0, default object detector) ===")
    config = _upsert(
        db,
        task=ModelTask.OBJECT_DETECTION,
        name="rf-detr-nano",
        license_="Apache-2.0",
        checkpoint_source=(
            "https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth "
            "(via the 'rfdetr' PyPI package)"
        ),
    )
    try:
        from rfdetr import RFDETRNano

        model = RFDETRNano()
        class_names = getattr(model, "class_names", None)
        config.supported_classes_json = None
        if class_names:
            config.supported_classes_json = json.dumps(list(class_names))
        config.is_available = True
        config.enabled = True  # Apache-2.0 default -- safe to enable automatically
        print("Downloaded and validated successfully. Enabled as the default detector.")
    except ImportError:
        config.is_available = False
        config.enabled = False
        print(
            "SKIPPED: the 'rfdetr' package is not installed. From backend/, run:\n"
            "  uv sync --extra rfdetr"
        )
    except Exception as exc:  # noqa: BLE001
        config.is_available = False
        config.enabled = False
        print(f"FAILED to download/load: {exc}")
        print(
            "Object detection will show 'not configured' until this is resolved. "
            "This commonly happens when the deployment's network cannot reach "
            "storage.googleapis.com -- check firewall/proxy rules."
        )
    db.commit()


def _try_download_yolo(db, checkpoint: str) -> None:
    name = checkpoint.replace(".pt", "")
    print(f"\n=== YOLO {name} (AGPL-3.0, opt-in adapter) ===")
    config = _upsert(
        db,
        task=ModelTask.OBJECT_DETECTION,
        name=name,
        license_="AGPL-3.0-only",
        checkpoint_source=(
            "https://github.com/ultralytics/assets/releases "
            f"(via the 'ultralytics' PyPI package, checkpoint={checkpoint})"
        ),
    )
    try:
        from ultralytics import YOLO

        model = YOLO(checkpoint)

        config.supported_classes_json = json.dumps(list(model.names.values()))
        config.is_available = True
        config.enabled = True
        print(
            "Downloaded and validated successfully. ENABLED -- you have accepted the "
            "AGPL-3.0 obligations for the 'ultralytics' package (see "
            "https://www.gnu.org/licenses/agpl-3.0.html and "
            "https://docs.ultralytics.com/help/license/)."
        )
    except ImportError:
        config.is_available = False
        config.enabled = False
        print(
            "SKIPPED: the 'ultralytics' package is not installed. From backend/, run:\n"
            "  uv sync --extra yolo"
        )
    except Exception as exc:  # noqa: BLE001
        config.is_available = False
        config.enabled = False
        print(f"FAILED to download/load: {exc}")
    db.commit()


def _register_weapon_detector(db, onnx_path: str) -> None:
    print("\n=== Weapon detector (fine-tuned YOLO11n, ONNX) ===")
    print(
        "This is NOT a pretrained checkpoint you can download -- it must be trained "
        "locally first. See docs/MODEL_REGISTRY.md and scripts/weapon_detection/ for "
        "the full dataset-prep -> train -> evaluate -> export pipeline.\n"
        "Because training uses 'ultralytics' (AGPL-3.0), enabling this checkpoint "
        "carries the same AGPL-3.0 obligations as the YOLO object-detection adapter."
    )
    config = _upsert(
        db,
        task=ModelTask.WEAPON_DETECTION,
        name="weapon-detector-yolo11n-onnx",
        license_=(
            "AGPL-3.0-only (training framework); "
            "dataset CC BY-SA 4.0 (ari-dasci/OD-WeaponDetection)"
        ),
        checkpoint_source="Locally trained -- see scripts/weapon_detection/",
    )

    if not os.path.exists(onnx_path):
        config.is_available = False
        config.enabled = False
        print(f"FAILED: no ONNX file found at {onnx_path}.")
        print(
            "Run, in order:\n"
            "  python scripts/weapon_detection/prepare_dataset.py "
            "--source-dir <dataset> --output-dir <out>\n"
            "  python scripts/weapon_detection/train.py "
            "--dataset <out>/dataset.yaml --output-dir <model-out>\n"
            "  python scripts/weapon_detection/export_onnx.py "
            "--checkpoint <model-out>/train/weights/best.pt"
        )
        db.commit()
        return

    try:
        import onnxruntime as ort

        session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        del session  # just validating it loads
        config.checkpoint_path = onnx_path
        config.supported_classes_json = json.dumps(
            ["pistol", "smartphone", "knife", "monedero", "billete", "tarjeta"]
        )
        config.is_available = True
        config.enabled = True
        print(f"Registered and ENABLED weapon detector at {onnx_path}.")
        print(
            "IMPORTANT: see docs/LIMITATIONS.md for this checkpoint's actual measured "
            "accuracy before relying on it for anything beyond a demo -- it was trained "
            "on a small subset for a small number of epochs in this project's own "
            "development environment, not to production quality."
        )
    except Exception as exc:  # noqa: BLE001
        config.is_available = False
        config.enabled = False
        print(f"FAILED to load ONNX model: {exc}")
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-yolo-agpl",
        metavar="CHECKPOINT",
        nargs="?",
        const="yolo11n.pt",
        default=None,
        help=(
            "Also download and enable the optional YOLO adapter (AGPL-3.0-only). "
            "Optionally pass a checkpoint name, e.g. yolo26n.pt (default: yolo11n.pt)."
        ),
    )
    parser.add_argument(
        "--enable-weapon-detector",
        metavar="ONNX_PATH",
        default=None,
        help=(
            "Register and enable a locally-trained weapon detector from the given "
            "ONNX file path (produced by scripts/weapon_detection/export_onnx.py). "
            "Same AGPL-3.0 considerations as --enable-yolo-agpl -- see docs/MODEL_REGISTRY.md."
        ),
    )
    args = parser.parse_args()

    print("SmartVision — model download & registry setup\n")

    with SessionLocal() as db:
        _try_download_rfdetr_nano(db)

        if args.enable_yolo_agpl:
            print(
                "\nYou have requested the AGPL-3.0 YOLO adapter. By continuing, you "
                "confirm you accept the AGPL-3.0 obligations that apply to any "
                "software you distribute that links against the 'ultralytics' "
                "package. See docs/MODEL_REGISTRY.md."
            )
            _try_download_yolo(db, args.enable_yolo_agpl)
        else:
            print(
                "\nSkipping the optional AGPL-3.0 YOLO adapter (not requested). "
                "Pass --enable-yolo-agpl to download and enable it."
            )

        if args.enable_weapon_detector:
            _register_weapon_detector(db, args.enable_weapon_detector)
        else:
            print(
                "\nSkipping weapon detector registration (not requested). "
                "Pass --enable-weapon-detector <path-to-onnx> once you've trained one "
                "(see scripts/weapon_detection/)."
            )

    print("\nDone. Restart the backend for camera workers to pick up the change:")
    print("  docker compose restart backend   (Docker)")
    print("  # or just re-run uvicorn in a dev setup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
