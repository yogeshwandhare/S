# Limitations

This document is updated as milestones land. It exists so nobody — including
us — overstates what SmartVision actually does.

## Status as of Milestone 2

**RF-DETR Nano's checkpoint could not be downloaded in this project's
development sandbox.** Two separate facts, both verified directly rather
than assumed:

1. The `rfdetr` PyPI package itself was not installed in the sandbox this
   was built in, due to that sandbox's limited disk space (a constraint of
   the development environment, not of the model or the package).
2. Separately, the checkpoint `rfdetr` downloads
   (`https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth`)
   was confirmed unreachable through that same sandbox's network egress
   policy (a `curl -I` to `storage.googleapis.com` was blocked there).

Neither of these is expected to be a problem on a normal machine with
regular internet access and a few hundred MB of free disk -- `pip install
rfdetr` and its automatic checkpoint download are the package's normal,
documented behavior. The `RFDetrNanoDetector` adapter
(`vision_worker/vision_worker/detectors/rfdetr_detector.py`) is written
against the real, current `rfdetr` package API (verified from the
installed package's source, not from memory) but has not been exercised
end-to-end. Run `scripts/download_models.py` on a machine with normal
network access to validate it there.

**The opt-in YOLO adapter (`ultralytics`, AGPL-3.0-only) was fully
downloaded, run, and verified end-to-end** in the same sandbox: real
weights downloaded from `github.com/ultralytics/assets` releases, real
inference run on a real photograph (correctly detected a bus and four
people), wired through the real tracker and camera worker, and confirmed
live over the actual MJPEG streaming endpoint. This is what proves the
ingest → detect → track → annotate pipeline architecture is sound --
independent of which specific detector ends up enabled in a given
deployment.

## Status as of Milestone 4

Weapon detection and an aggressive-motion heuristic now exist. **Neither
should be treated as production-ready:**

- The weapon detector was fine-tuned for 3 epochs on a small data subset in
  this project's own resource-constrained development environment (see
  `docs/MODEL_REGISTRY.md` for the exact, real, measured accuracy numbers
  and exactly why the subset is small). It correctly identifies that
  *something weapon-like* is present often enough to be a useful review
  signal, but its per-class accuracy is nowhere near what a deployed
  safety system needs, and it will misclassify which weapon it saw (a real
  example: a pistol labeled "knife"). Every weapon incident is explicitly
  "possible weapon, review required" for exactly this reason.
- There is still no validated fight/violence classifier. The
  aggressive-motion heuristic is motion-only (two people, close together,
  both moving fast, sustained across several frames) and will produce
  false positives on dancing, contact sports, rough play, and dense crowd
  movement -- this is an accepted, documented limitation of a heuristic
  that has no access to pose or action information, not a bug to be
  quietly patched. Every such incident is labeled "Aggressive motion --
  review required", never "Fight confirmed".
- Pose estimation (MediaPipe or MMPose) was not integrated. The
  aggressive-motion heuristic relies only on bounding-box motion, not body
  pose -- a real fight-detection system would benefit substantially from
  pose information, which is a natural next step, not something this
  project claims to already do.

## Status as of Milestone 6 (final)

This is the final milestone. `docs/IMPLEMENTATION_REPORT.md` is the
authoritative summary of what was built, what wasn't, and what was
measured versus assumed -- read that first. This file remains the living,
detailed limitations list; nothing below is superseded by the report, they
complement each other.

Two things added this milestone:
- `scripts/benchmark.py` produced real, measured detector and pipeline
  throughput numbers on this project's actual (1-CPU-core) development
  hardware -- see `docs/benchmark_report.json`. Pipeline throughput scales
  down roughly proportionally as camera count increases, exactly as
  expected for CPU-bound work sharing one core. No claim is made about
  performance on different hardware.
- Demo Mode (`/api/demo`, and the Demo Mode dashboard page) launches a
  clearly-labeled sample-video camera. It is not a separate code path from
  regular file-source cameras -- it is the same pipeline, with a "DEMO
  MODE" label attached, because that is the honest way to demonstrate that
  detections shown in a demo are the same real detections the rest of the
  app produces, not a scripted simulation.

## Status as of Milestone 5

Notifications, analytics, user management, and audit logging now exist.
Two things worth knowing:

- **The notification worker is a single in-process asyncio task, not a
  distributed queue.** It polls the database every 15 seconds from
  whichever backend process is running. This is correct and sufficient for
  the single-`uvicorn`-worker deployment this project documents, but if
  you ever run multiple backend replicas, each would poll independently --
  fine for correctness (no duplicate sends, since each notification row is
  only processed once its status changes), but not optimized for that
  scale. The same caveat already applies to the login rate limiter (see
  below).
- **Analytics are only as good as the incident data behind them.** A
  fresh deployment's Analytics page will show all zeros, not placeholder
  charts -- there is no synthetic data path. The response-time metric only
  reflects incidents that have actually been acknowledged; it does not
  estimate anything for incidents still awaiting review.

## Structural limitations that will remain true even once later milestones ship

- **Per-camera tracking only.** SmartVision does not implement cross-camera
  identity matching or any form of re-identification. A person tracked in
  Camera A and later seen in Camera B is treated as two unrelated tracks.
- **No facial recognition, biometrics, or emotion detection**, by design —
  not a gap to be filled later.
- **Human-in-the-loop only.** No detection category ever results in an
  automatic call to police, an automatic penalty, or a system-generated
  claim that a specific person committed a specific act. Every incident is
  AI-flagged and requires human review; AI confidence and human confirmation
  are always stored and displayed as two separate fields.
- **CPU-only is the baseline assumption.** GPU acceleration is auto-detected
  and used when available, but no feature ever promises a specific FPS
  without a benchmark run on the actual deployment hardware (see
  `scripts/benchmark.py`, added in Milestone 6).
- **Single-process login rate limiting.** The login rate limiter
  (`app/core/rate_limit.py`) is in-memory and per-process. It is correct for
  the single-`uvicorn`-worker deployment this README documents, but does not
  protect a multi-worker or multi-replica deployment against distributed
  brute-force attempts. A Redis-backed limiter would be needed for that.
- **MJPEG streaming baseline.** The initial live-view implementation
  (Milestone 2) uses MJPEG over HTTP, which is simple and broadly
  compatible but higher-bandwidth than WebRTC and not ideal for many
  simultaneous high-resolution viewers. WebRTC is an explicitly optional
  future enhancement, not part of the MVP.
- **Weapon and fight/aggressive-motion detection are heuristic/limited-accuracy, by measured fact, not assumption.** See `docs/MODEL_REGISTRY.md` for the weapon detector's real evaluation numbers and the aggressive-motion heuristic's known false-positive modes. Neither ever asserts a confirmed weapon or a confirmed fight -- both categories exist solely to route candidates to a human reviewer.
- **Not a certified emergency-response system.** This is a decision-support
  prototype for a student/portfolio project. It has not been validated
  against any regulatory or safety-certification standard and should not be
  relied on as a sole safety measure.

## Known false-positive risk areas (measured or directly observed, not assumed)

- The aggressive-motion heuristic is expected to trigger on dancing,
  sports, hugging, and dense crowd movement, since it has no access to
  pose or action information -- only bounding-box motion. This is covered
  by its own test suite's false-positive guards (a single fast person
  never triggers it; a person and a stationary object never pair), but
  those guards narrow the failure mode, they don't eliminate it.
- The weapon detector, trained on a small subset for very few epochs (see
  `docs/MODEL_REGISTRY.md`), has real measured recall around 0.27 on held-
  out data -- it will miss a meaningful fraction of real weapons in frame,
  and its class label (pistol vs. knife) is not reliable even when it does
  detect something. Its practical value in its current state is as a
  coarse "something weapon-like is present" signal, not a reliable
  classifier.
- Abandoned-object detection can misfire under occlusion, camera movement,
  or when a group temporarily steps away from shared luggage (e.g. queuing).
- Lighting changes, low-light footage, and camera compression artifacts all
  degrade detector accuracy; no claim about accuracy holds across untested
  lighting/camera conditions.

## What "measured performance" means here

Per `docs/BENCHMARKS.md` (populated starting Milestone 6), any FPS, latency,
or accuracy figure reported for this project will state exactly which
hardware, resolution, model, and dataset it came from. Absence of a number
means it has not been measured yet, not that it is assumed good.
