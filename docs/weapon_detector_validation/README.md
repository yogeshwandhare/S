# Weapon detector validation artifacts

Real output from `scripts/weapon_detection/evaluate.py`, run against the
actual checkpoint described in `docs/MODEL_REGISTRY.md` (YOLO11n fine-tuned
for 3 epochs on a 828-image subset of the Sohas dataset, evaluated on a
held-out 125-image test split never seen during training). Nothing here is
synthetic or illustrative -- these are the literal plots and sample
predictions ultralytics generated during that run.

- `confusion_matrix.png` / `confusion_matrix_normalized.png` -- per-class
  confusion matrix on the test split.
- `BoxP_curve.png`, `BoxR_curve.png`, `BoxF1_curve.png`, `BoxPR_curve.png`
  -- precision/recall/F1 curves across confidence thresholds.
- `val_batch*_labels.jpg` -- ground-truth boxes on three sample batches
  from the test split.
- `val_batch*_pred.jpg` -- this checkpoint's actual predictions on those
  same batches, at the confidence threshold ultralytics used for
  validation (0.001, its default for computing the full PR curve -- not
  the 0.4 threshold this project's camera pipeline actually uses at
  inference time, which is much more conservative).

See `docs/weapon_detector_evaluation_report.json` for the exact numeric
metrics, and `docs/MODEL_REGISTRY.md` for what these numbers mean in
practice and why this checkpoint is not production-ready.
