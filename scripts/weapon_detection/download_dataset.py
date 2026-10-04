"""Download a pinned Sohas YOLO dataset, verifying Git blob hashes.

Keeps the upstream test set untouched. Group recognizable "frame" filenames
by recording prefix for train/validation. Other images are split individually;
unknown recording provenance means this is not a scene-independent benchmark.
Source and license documents are saved with the downloaded data.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import re
import time
import threading
from urllib.parse import quote

import requests

REPOSITORY = "ari-dasci/OD-WeaponDetection"
REVISION = "48860b990e4d4f57fe100248887fceb248475dc8"
TREE = "62b71bc546128e79632ae2fc8f505f6fdc01617f"
PREFIX = "Weapons and similar handled objects/Sohas_weapon-Detection-YOLOv5/"
NAMES = ["pistol", "smartphone", "knife", "monedero", "billete", "tarjeta"]
_LOCAL = threading.local()


def fetch(url: str) -> bytes:
    if not hasattr(_LOCAL, "session"):
        _LOCAL.session = requests.Session()
    for attempt in range(4):
        try:
            response = _LOCAL.session.get(url, timeout=45)
            response.raise_for_status()
            return response.content
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    index = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{TREE}?recursive=1"))
    if index.get("truncated"):
        raise RuntimeError("Dataset index is incomplete")
    entries = {e["path"]: e for e in index["tree"] if e["type"] == "blob"}
    images = [p for p in entries if re.fullmatch(r"obj_train_data/images/(train|test)/[^/]+\.jpg", p)]
    train_groups = sorted({re.split(r"frame", Path(p).stem)[0] for p in images if "/train/" in p})
    if len(train_groups) < 3:
        raise RuntimeError("Cannot form independent recording groups")
    random.Random(42).shuffle(train_groups)
    val_groups = set(train_groups[:max(1, round(len(train_groups) * .15))])
    jobs = []
    manifest = []
    for path in sorted(images):
        label = path.replace("/images/", "/labels/").removesuffix(".jpg") + ".txt"
        if label not in entries:
            raise RuntimeError(f"Missing annotation: {label}")
        group = re.split(r"frame", Path(path).stem)[0]
        split = "test" if "/test/" in path else "val" if group in val_groups else "train"
        for source, kind in [(path, "images"), (label, "labels")]:
            jobs.append((source, root / kind / split / Path(source).name))
        manifest.append({"source": path, "split": split, "recording": group, "sha": entries[path]["sha"]})

    def download(job: tuple[str, Path]) -> None:
        source, target = job
        expected = entries[source]["sha"]
        def valid(data: bytes) -> bool:
            return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == expected
        if target.exists() and valid(target.read_bytes()):
            return
        data = fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{quote(PREFIX + source)}")
        if not valid(data):
            raise RuntimeError(f"Hash mismatch: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            try:
                target.write_bytes(data)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    print(f"Downloading {len(images)} labeled images ({sum(entries[p]['size'] for p in images) / 1e6:.0f} MB)", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for count, _ in enumerate(pool.map(download, jobs), 1):
            if count % 200 == 0:
                print(f"Verified {count}/{len(jobs)} files", flush=True)
    for name in ["License.md", "README.md"]:
        (root / ("UPSTREAM_" + name)).write_bytes(fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{name}"))
    counts = {s: sum(m["split"] == s for m in manifest) for s in ["train", "val", "test"]}
    # Fail before training if a split lacks any class or annotations are malformed.
    distributions = {}
    for split in counts:
        classes = [0] * len(NAMES)
        for label in (root / "labels" / split).glob("*.txt"):
            for line in label.read_text().splitlines():
                fields = line.split()
                if not fields:
                    continue
                if len(fields) != 5 or not 0 <= int(fields[0]) < len(NAMES):
                    raise ValueError(f"Invalid annotation: {label}")
                if not all(0 <= float(v) <= 1 for v in fields[1:]):
                    raise ValueError(f"Invalid bounding box: {label}")
                classes[int(fields[0])] += 1
        if not all(classes):
            raise ValueError(f"Missing class in {split}: {classes}")
        distributions[split] = dict(zip(NAMES, classes))
    (root / "dataset.yaml").write_text(f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {NAMES}\n")
    (root / "provenance.json").write_text(json.dumps({
        "repository": f"https://github.com/{REPOSITORY}", "revision": REVISION,
        "license_note": "Upstream License.md says CC BY 4.0; README says CC BY-SA 4.0. Both preserved; retain attribution and share-alike when redistributing data.",
        "split_policy": "Original test preserved; training recordings grouped by prefix before frame; 15% validation groups, seed 42. Upstream test may share recordings with training.",
        "counts": counts, "class_counts": distributions, "images": manifest,
    }, indent=2))
    print(json.dumps({"counts": counts, "class_counts": distributions}), flush=True)


if __name__ == "__main__":
    main()
