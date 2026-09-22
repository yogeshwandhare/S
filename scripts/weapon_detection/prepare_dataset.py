#!/usr/bin/env python3
"""
Prepare the weapon-detection training dataset.

Data source: the "Sohas" weapons dataset from the OD-WeaponDetection
project (University of Granada, ari-dasci research group), published in:

    Pérez-Hernández, F., Tabik, S., Lamas, A., Olmos, R., Fujita, H.,
    Herrera, F. (2020). Object Detection Binary Classifiers methodology
    based on deep learning to identify small objects handled similarly:
    Application in video surveillance. Knowledge-Based Systems, 194,
    105590. https://doi.org/10.1016/j.knosys.2020.105590

Repository: https://github.com/ari-dasci/OD-WeaponDetection
License: CC BY-SA 4.0 (see that repository's License.md) -- this script
does not redistribute the dataset; it documents where to get it and how
to prepare it. If you re-share the prepared dataset, you must credit the
source and share alike under the same license.

The dataset deliberately includes near-miss "similar handled objects" as
negative-adjacent classes (smartphone, purse, banknote, card) alongside
pistol and knife -- exactly the negative-example requirement called out in
the project brief ("include negative examples such as phones, tools,
umbrellas, and harmless objects").

Usage:
    python scripts/weapon_detection/prepare_dataset.py \
        --source-dir /path/to/downloaded/Sohas_weapon-Detection-YOLOv5 \
        --output-dir data/weapon_detection

This splits the available images into train/val/test (default 70/15/15,
seeded for reproducibility) and writes a `dataset.yaml` ultralytics can
train directly against.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

CLASS_NAMES = ["pistol", "smartphone", "knife", "monedero", "billete", "tarjeta"]
# English labels shown in the UI/registry -- the underlying dataset uses
# Spanish names for three classes (monedero=purse/wallet, billete=banknote,
# tarjeta=card); kept as an explicit mapping rather than silently renaming
# the dataset's own class list, so provenance stays traceable.
CLASS_DISPLAY_NAMES = {
    "pistol": "pistol",
    "smartphone": "smartphone",
    "knife": "knife",
    "monedero": "purse_wallet",
    "billete": "banknote",
    "tarjeta": "card",
}


def find_image_label_pairs(source_dir: Path) -> list[tuple[Path, Path]]:
    images_dir = source_dir / "obj_train_data" / "images" / "test"
    labels_dir = source_dir / "obj_train_data" / "labels" / "test"
    if not images_dir.exists():
        # Fall back to the "train" split name if that's what was downloaded
        # instead (the full dataset's train/ directory has the same layout).
        images_dir = source_dir / "obj_train_data" / "images" / "train"
        labels_dir = source_dir / "obj_train_data" / "labels" / "train"
    if not images_dir.exists():
        print(f"Could not find an images directory under {source_dir}", file=sys.stderr)
        sys.exit(1)

    pairs = []
    for image_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{image_path.stem}.txt"
        if label_path.exists():
            pairs.append((image_path, label_path))
    return pairs


def write_split(pairs: list[tuple[Path, Path]], split_name: str, output_dir: Path) -> None:
    images_out = output_dir / "images" / split_name
    labels_out = output_dir / "labels" / split_name
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)
    for image_path, label_path in pairs:
        shutil.copy2(image_path, images_out / image_path.name)
        shutil.copy2(label_path, labels_out / label_path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    pairs = find_image_label_pairs(args.source_dir)
    if not pairs:
        print(f"No image/label pairs found under {args.source_dir}", file=sys.stderr)
        return 1
    print(f"Found {len(pairs)} labeled images.")

    rng = random.Random(args.seed)
    rng.shuffle(pairs)

    n_train = int(len(pairs) * args.train_fraction)
    n_val = int(len(pairs) * args.val_fraction)
    train_pairs = pairs[:n_train]
    val_pairs = pairs[n_train : n_train + n_val]
    test_pairs = pairs[n_train + n_val :]

    print(f"Split: {len(train_pairs)} train / {len(val_pairs)} val / {len(test_pairs)} test")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_split(train_pairs, "train", args.output_dir)
    write_split(val_pairs, "val", args.output_dir)
    write_split(test_pairs, "test", args.output_dir)

    dataset_yaml = args.output_dir / "dataset.yaml"
    dataset_yaml.write_text(
        "# Prepared by scripts/weapon_detection/prepare_dataset.py\n"
        "# Source: https://github.com/ari-dasci/OD-WeaponDetection (CC BY-SA 4.0)\n"
        f"path: {args.output_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {CLASS_NAMES}\n"
    )
    print(f"Wrote {dataset_yaml}")

    # Report class distribution per split so an imbalanced split is visible
    # immediately, not discovered after a confusing training run.
    for split_name, split_pairs in [
        ("train", train_pairs),
        ("val", val_pairs),
        ("test", test_pairs),
    ]:
        counts = [0] * len(CLASS_NAMES)
        for _, label_path in split_pairs:
            for line in label_path.read_text().splitlines():
                if line.strip():
                    counts[int(line.split()[0])] += 1
        print(
            f"  {split_name}: "
            + ", ".join(f"{n}={c}" for n, c in zip(CLASS_NAMES, counts, strict=True))
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
