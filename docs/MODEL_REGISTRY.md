# Model Registry & License Inventory

This is the single source of truth for every AI checkpoint SmartVision uses:
where it comes from, what license governs it, exactly what classes it
supports, and whether it's currently enabled. The `model_configs` database
table (see `backend/app/models/model_config.py`) mirrors this at runtime;
`scripts/download_models.py` is what actually populates it -- there is no
HTTP endpoint that can enable a model, by design (see that script's
docstring).

## Object detection

| Model | License | Package / source | Status |
|---|---|---|---|
| **RF-DETR Nano** (default) | Apache-2.0 | `rfdetr` on PyPI; checkpoint auto-downloaded from `storage.googleapis.com/rfdetr/nano_coco/` | Adapter written and code-complete (`vision_worker/vision_worker/detectors/rfdetr_detector.py`), but **not yet verified end-to-end** -- see `docs/LIMITATIONS.md` for exactly why (a development-sandbox network/disk constraint, not a defect in the model or package). Run `scripts/download_models.py` to validate on your machine. |
| **YOLO11n / YOLO26n** (opt-in adapter) | **AGPL-3.0-only** | `ultralytics` on PyPI; checkpoint auto-downloaded from `github.com/ultralytics/assets` releases | **Verified working end-to-end**: downloaded, ran real inference, correctly detected real objects in a test photo, confirmed live through the MJPEG streaming endpoint. Never enabled by default -- `scripts/download_models.py --enable-yolo-agpl` requires an explicit, printed acknowledgement of the AGPL-3.0 obligations before enabling it. |
| RT-DETRv2 | Apache-2.0 | Reference implementation at `github.com/lyuwenyu/RT-DETR` | **Deliberately not implemented.** Its checkpoints are downloadable (confirmed: hosted on `github.com/lyuwenyu/storage` releases), but the reference repo is a research codebase with no pip-installable package or stable API -- it expects you to run scripts from within a clone using its own YAML-based config/registry system. Vendoring that correctly, under the time available, risked shipping glue code that looks plausible but hasn't actually been proven to load the checkpoint correctly. RF-DETR Nano (a real pip package with a clean, verified API) already satisfies the "Apache-2.0 default" requirement, so this was deferred rather than shipped half-verified. |

## Pose estimation

**Not yet implemented** -- deferred (see `docs/LIMITATIONS.md`).

## Weapon detection

| Model | License | Source | Status |
|---|---|---|---|
| **Fine-tuned YOLO11n, ONNX** | AGPL-3.0-only (training framework: `ultralytics`); dataset CC BY-SA 4.0 | Trained locally via `scripts/weapon_detection/` on the Sohas dataset (`github.com/ari-dasci/OD-WeaponDetection`, University of Granada) | **Trained, evaluated, and verified live end-to-end** -- see below for exactly what "trained" means here and its real, measured accuracy. |
| **Weapons-and-Knives YOLOv8** (optional) | Upstream README claims MIT, GitHub repository is labeled GPL-3.0; Ultralytics runtime is AGPL-3.0 | [JoaoAssalim/Weapons-and-Knives-Detector-with-YOLOv8](https://github.com/JoaoAssalim/Weapons-and-Knives-Detector-with-YOLOv8), checkpoint expected at `runs/detect/Normal_Compressed/weights/best.pt` | Adapter/registry support added. Must be loaded from a local `.pt` file and explicitly enabled with `scripts/download_models.py --enable-weapons-yolov8 <path>`. The model is not included in this repository; validate licensing and detection quality before deployment. |
| **CLIP ViT-B/32 violence triage** (optional) | Upstream violence-detection repository declares no license; OpenCLIP library is MIT | [sukhitashvili/violence-detection](https://github.com/sukhitashvili/violence-detection), OpenAI ViT-B/32 weights loaded with `open-clip-torch` and cached in `models/clip/` | Integrated as a frame-level zero-shot classifier using the upstream scene prompts. It is not a temporal action model and its cosine similarity is not a calibrated probability. Three repeated fight/violence labels create a human-review incident; validate before deployment. |

## Abandoned-object classification

The existing luggage rule requires a backpack, handbag, or suitcase to remain
stationary for 60 seconds with no person nearby. An optional classifier can
then confirm the candidate from its image crop. Enable it only if the supplied
checkpoint is a YOLO classification model and has a luggage class such as
`bag`, `backpack`, `handbag`, `suitcase`, or `luggage`; registration validates
both facts. This checkpoint classifies luggage types; it does not determine
whether an item is abandoned. The existing dwell-time and owner-distance rule
determines candidate status.
The upstream README describes a YOLO11 classifier and warns that its examples
depend on a fixed camera/background and stable lighting. Its repository does
not declare a license; the Ultralytics runtime is AGPL-3.0.

Clone [erwinyo/Abandoned-Object-Detection](https://github.com/erwinyo/Abandoned-Object-Detection),
copy `cls-model.pt` to `models/abandoned/cls-model.pt`, rebuild the backend, and
run:

```powershell
docker compose exec backend python scripts/download_models.py --enable-abandoned-object-classifier /models/abandoned/cls-model.pt
docker compose restart backend
```

If the checkpoint labels do not meet the validation rule, registration remains
disabled and prints the labels it found. Alerts remain candidates for human
review, not claims that an object is dangerous.

**Dataset**: the Sohas weapons dataset from Pérez-Hernández et al.,
*"Object Detection Binary Classifiers methodology based on deep learning
to identify small objects handled similarly: Application in video
surveillance"*, Knowledge-Based Systems 194 (2020), 105590
(https://doi.org/10.1016/j.knosys.2020.105590). Repository:
`github.com/ari-dasci/OD-WeaponDetection`, license CC BY-SA 4.0. This
dataset deliberately includes near-miss "similar handled objects"
(smartphone, purse, banknote, card) alongside pistol and knife -- exactly
the negative-example requirement the project brief calls for.

**What was actually done, and its real constraints**: this development
environment has a single CPU core and a hard disk-space budget, so only
the dataset's 857-image "test" split was downloaded (the full dataset,
which includes a much larger train split, is several GB) and further
divided 70/15/15 into train/val/test for this pipeline
(`scripts/weapon_detection/prepare_dataset.py`, seeded for
reproducibility). A YOLO11n base checkpoint was fine-tuned for **3 epochs**
at 320x320 on CPU (`scripts/weapon_detection/train.py`) -- enough to prove
the training pipeline is mechanically correct, nowhere near enough for a
production-quality model. Real, measured results on the held-out test
split (`scripts/weapon_detection/evaluate.py`; full numbers in
`docs/weapon_detector_evaluation_report.json`; confusion matrix, PR
curves, and real sample predictions in
`docs/weapon_detector_validation/`):

| Metric | Value |
|---|---|
| Precision (overall) | 0.66 |
| Recall (overall) | 0.27 |
| mAP50 (overall) | 0.30 |
| mAP50-95 (overall) | 0.19 |
| Pistol mAP50 | 0.28 |
| Knife mAP50 | 0.37 |
| Inference latency (CPU) | ~15.3 ms/image |

Verified live: a real image of a person holding a pistol at a shooting
range, run through the full camera pipeline, produced a real `Incident`
row -- though the model labeled the weapon "knife" rather than "pistol", a
real classification error consistent with the modest recall above. The
system still correctly flagged it as "possible weapon, review required"
-- which is the safety-relevant outcome, and exactly why this category
never asserts a confirmed classification. **Do not treat this checkpoint
as production-ready.** A real deployment should retrain on the full
upstream dataset for many more epochs, ideally on a GPU, and re-run
`evaluate.py` before trusting the numbers.

Because training used `ultralytics` (AGPL-3.0), this checkpoint carries
the same licensing treatment as the optional YOLO object-detection
adapter: never enabled by default, and `scripts/download_models.py
--enable-weapon-detector <path>` requires the same explicit
acknowledgement.

The linked YOLOv8 checkpoint can also run through the weapon alert pipeline.
For Docker, copy its `.pt` file to `models/weapons/yolov8-best.pt`, then
rebuild the backend with `docker compose up -d --build backend`. Register it
inside the container so the database and checkpoint paths match:
`docker compose exec backend python scripts/download_models.py --enable-weapons-yolov8 /models/weapons/yolov8-best.pt`.
Registration validates the checkpoint and reads its class labels. Camera
workers create possible-weapon incidents after repeated detections; incidents
remain pending human review. The upstream README's MIT claim conflicts with
GitHub's GPL-3.0 repository classification, and Ultralytics is AGPL-3.0, so
resolve licensing for your use before enabling it in a distributed deployment.

## Fight / aggressive-activity recognition

An optional CLIP-based frame classifier is available for violence triage.
Enable it with `docker compose up -d --build backend`, then
`docker compose exec backend python scripts/download_models.py --enable-violence-detection`,
and restart the backend. It samples each active camera at up to one frame per
second, selects the closest scene prompt, and requires three consecutive
violence labels before creating a **possible violence -- review required**
incident. CLIP cosine similarity is not a probability, the classifier is not
temporal, and it is not production-validated. The upstream repository has no
declared license; its code is not vendored here.

The existing motion rule also evaluates motion between tracked people with
a heuristic (`vision_worker/vision_worker/rules/aggressive_motion.py`):
two or more people in close proximity, each moving rapidly, sustained
across several consecutive frames. This is deliberately conservative about
what it claims -- every incident it creates is labeled **"Aggressive
motion -- review required"**, never "fight confirmed", and it is expected
to also fire on dancing, contact sports, and rough play (see
`docs/LIMITATIONS.md`). Tested with 9 synthetic-fixture unit tests
covering the false-positive guards (a single fast-moving person never
triggers it; a person and a stationary object never form a pair; a single
frame of fast motion isn't "sustained").

## Rules this inventory follows

1. Every row above has a real, verified download source and license before
   its corresponding detector is enabled in the UI -- "verified" here means
   actually downloaded and run, not just found in documentation.
2. The AGPL-3.0 YOLO adapter (and the weapon detector, trained with the
   same framework) is never enabled by default and is never silently
   bundled into a build presented as permissively licensed -- enabling
   either requires a separate, explicit flag and prints the licensing
   obligation before doing anything.
3. A checkpoint is never described as supporting a class (e.g. "knife") it
   wasn't actually trained to recognize. All detector adapters read class
   names directly from the loaded checkpoint's own metadata
   (`Detector.class_names`), never from an assumed/hardcoded list.
4. If a checkpoint can't be downloaded, trained, or validated,
   `is_available` stays `false` and the corresponding feature shows "not
   configured" in the dashboard -- it is never faked.
5. Every reported accuracy number (see the weapon-detector table above)
   comes from an actual evaluation run against held-out data, with the
   exact command and dataset split documented, never estimated or assumed.
