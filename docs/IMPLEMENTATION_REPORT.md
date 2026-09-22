# SmartVision — Final Implementation Report

This report lists exactly what was built, what wasn't, and what was
actually measured versus assumed. Nothing here restates marketing claims
from the original brief — every line is either a fact about this
repository's code or a number produced by actually running it.

## Completed features

**Foundation (Milestone 1)**
- FastAPI backend, PostgreSQL + Alembic migrations, cookie-based JWT auth,
  RBAC (admin/operator/viewer), login rate limiting, audit logging.
- React 19 + TypeScript + Vite + Tailwind 4 dashboard shell with a working
  login flow and full navigation.
- Docker Compose (Postgres + backend + Caddy), documented non-Docker dev
  setup, `uv`-managed Python dependencies with a verified lockfile.

**Video pipeline (Milestone 2)**
- Camera ingest for RTSP (with TCP transport and SSRF-range blocking),
  local video files, and USB webcams, with reconnect/exponential backoff
  and credential-scrubbed logging.
- A `Detector` interface with two working adapters: RF-DETR Nano
  (Apache-2.0, the documented default -- code-complete but not verified in
  this development sandbox, see Limitations below) and YOLO11n/YOLO26n via
  `ultralytics` (AGPL-3.0, opt-in only, fully verified with real inference).
- A SORT-style IoU tracker (no cross-camera identity matching, by design).
- Live annotated MJPEG streaming.
- Model registry with an explicit, non-HTTP enable flow
  (`scripts/download_models.py`).

**Reliable incidents (Milestone 3)**
- Zone editor (click-to-draw polygons over the live feed) with
  point-in-polygon intrusion detection, configurable dwell time and
  cooldown.
- Abandoned-object detection (stationarity + owner-proximity, with
  jitter tolerance and relocation handling).
- A rule-engine-to-incident pipeline: real triggers create persisted
  `Incident` rows with saved JPEG evidence snapshots and a database-level
  dedup safety net.
- Full incident review workflow (acknowledge/resolve/false-positive,
  notes, audit timeline) with RBAC-gated actions.

**Advanced AI (Milestone 4)**
- A real weapon detector: dataset sourced, prepared, and used to actually
  fine-tune, evaluate, and export a checkpoint (see Measured Performance
  below for the honest numbers). Runs via ONNX Runtime with a temporal
  confirmation rule (several consecutive frames required before alerting).
- An aggressive-motion heuristic (two-plus people, close together, both
  moving fast, sustained across frames) -- the project brief's own
  documented fallback for when no validated fight classifier exists.
  Always "review required," never "confirmed."

**Operations (Milestone 5)**
- Notification outbox: real SMTP email sending, exponential backoff retry,
  deduplication, a background asyncio worker (polled, no external queue).
  In-app notifications with read/unread state.
- Real analytics computed from actual incident records (trend, category/
  severity/camera breakdowns, response time from real acknowledgements).
- User management (create/deactivate/reactivate) and a full audit log
  viewer, both admin-only.

**Verification (Milestone 6)**
- This report.
- `scripts/benchmark.py`: measures real detector latency/FPS/memory and
  real multi-camera pipeline throughput on the actual hardware this
  project was developed on (see Measured Performance).
- Demo Mode: a dedicated page that launches a clearly-labeled sample-video
  camera (`GET/POST /api/demo`) -- verified live end-to-end.
- 172 automated tests passing across the backend and vision pipeline (see
  Test Results below), ruff and mypy clean on both Python packages.

## Partially completed / explicitly deferred features

- **RF-DETR Nano (the documented default detector) has not been verified
  end-to-end.** Its checkpoint host (`storage.googleapis.com`) was
  confirmed unreachable from this project's development sandbox, and the
  `rfdetr` package itself was never installed there due to that sandbox's
  disk constraints. The adapter code is written against the real,
  installed package's API. Run `scripts/download_models.py` on a machine
  with normal internet access to validate it there.
- **RT-DETRv2 was not implemented.** Its reference implementation has no
  pip-installable package or stable API; vendoring it correctly under time
  constraints risked shipping unverified glue code. RF-DETR Nano already
  satisfies the "Apache-2.0 default" requirement on paper; see the
  point above for its actual verification status.
- **The weapon detector is not production-ready**, by measured fact (see
  below), not assumption. It was fine-tuned for 3 epochs on an 828-image
  subset of a larger public dataset, due to this project's single-CPU-core,
  disk-constrained development environment. It correctly identifies that
  *something weapon-like* is present often enough to be a useful review
  signal, but its per-class accuracy and recall are well below what a
  deployed safety system needs.
- **No validated fight/violence classifier exists.** The aggressive-motion
  heuristic is a documented, intentional fallback, not a stand-in that
  will silently become "real" later without further work -- see
  `docs/MODEL_REGISTRY.md`.
- **Pose estimation (MediaPipe/MMPose) was not integrated.** The
  aggressive-motion heuristic uses only bounding-box motion.
- **No evidence-retention cleanup job was implemented.**
  `EVIDENCE_RETENTION_DAYS` exists as a documented setting but nothing
  currently reads it to delete old snapshots automatically -- a real
  gap, not a documentation omission.
- **The notification worker is a single in-process asyncio task**, not a
  distributed queue -- correct for the single-`uvicorn`-worker deployment
  this project documents, not horizontally scaled.
- **WebRTC was not implemented.** MJPEG is the only live-streaming
  transport, as scoped from Milestone 2 onward.

## Test results

Run on this project's actual development machine (see Hardware below),
via `uv run --with pytest pytest tests/` (backend) and the equivalent for
`vision_worker/tests/`:

| Suite | Passed | Skipped | Notes |
|---|---|---|---|
| Backend (`backend/tests/`) | 85 | 0 | Auth, RBAC, cameras, zones, incidents, notifications, analytics, users, audit logs, demo mode |
| Vision worker (`vision_worker/tests/`) | 87 | 1 | Geometry, tracker, rules (intrusion/abandoned-object/aggressive-motion/weapon-confirmation), camera worker, weapon detector, one real end-to-end inference test |

The one skipped vision-worker test requires a locally-trained weapon
checkpoint at a conventional path and is not expected to run in a fresh
clone. `ruff check` and `mypy` are clean on both `backend/app/` and
`vision_worker/vision_worker/`.

Real bugs caught and fixed during development, not merely avoided:
enum `.name` vs `.value` storage mismatch (Milestone 1), a rate-limiter
test-isolation leak (Milestone 1), a lifespan touching the wrong database
during API unit tests (Milestone 2), a stale test assumption about
immediate camera-error timing (Milestone 2), a loop-variable type-
narrowing bug across four rule-dispatch branches (Milestone 4), and
Python's `dict()` silently misinterpreting a SQLAlchemy `Result` as
mapping-like via its `.keys()` method, breaking every analytics
aggregation query (Milestone 5). Each is described, with its fix, in that
milestone's git commit message.

## Measured performance

**Hardware this was measured on** (from `docs/benchmark_report.json`,
produced by `scripts/benchmark.py`):
- 1 logical CPU core, 3.9 GB RAM, x86_64, Linux.
- This is a constrained development sandbox, not a representative "typical
  laptop" -- re-run `scripts/benchmark.py` on your actual deployment
  target before trusting these numbers there.

**Object detector (YOLO11n, 810×1080 frames, CPU)**:

| Metric | Value |
|---|---|
| Mean inference latency | 68.2 ms |
| Median / p95 latency | 66.9 ms / 84.1 ms |
| Detector-only FPS | 14.7 |
| Peak process RSS | 854 MB |

**Full pipeline throughput** (real `CameraWorker` instances, same shared
detector, scaling camera count on this 1-core machine):

| Cameras | Inference FPS per camera |
|---|---|
| 1 | 7.0 |
| 2 | 2.4 |
| 4 | 0.75 |

This clearly shows CPU-bound scaling on single-core hardware -- throughput
divides roughly proportionally as cameras are added, exactly as expected
when every camera's inference thread competes for the same core. **This
project makes no claim about FPS on multi-core hardware or with GPU
acceleration** -- those would need their own benchmark runs.

**Weapon detector** (see `docs/MODEL_REGISTRY.md` and
`docs/weapon_detector_evaluation_report.json` for the full numbers):
precision 0.66, recall 0.27, mAP50 0.30 (overall, held-out test split),
~15.3 ms/image inference latency. Explicitly not production-quality --
see Partially Completed Features above.

## License and provenance inventory

See `docs/MODEL_REGISTRY.md` for the complete, current inventory. Summary:

| Component | License | Verified how |
|---|---|---|
| RF-DETR Nano | Apache-2.0 | Package API verified; checkpoint download unverified in this sandbox |
| YOLO11n/26n (`ultralytics`) | AGPL-3.0-only, opt-in | Downloaded and run with real inference |
| Weapon detector training framework (`ultralytics`) | AGPL-3.0-only, opt-in | Same as above |
| Weapon detector training dataset (Sohas) | CC BY-SA 4.0 | Downloaded from `github.com/ari-dasci/OD-WeaponDetection`, provenance traced to its published paper |

## Known limitations

See `docs/LIMITATIONS.md` for the complete, living list, updated at every
milestone. It is not duplicated here to avoid the two documents drifting
out of sync with each other.
