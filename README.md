# SmartVision

An AI-assisted, human-reviewed public-safety surveillance platform: connects
to existing CCTV/IP cameras (or video files, or a USB webcam) and flags
restricted-zone intrusions, abandoned objects, aggressive motion, and
weapons for a human operator to review. Built local-first, on free and
open-source tools, to run on a student laptop or a small on-prem server —
not a cloud service.

**This is a decision-support prototype, not a certified emergency-response
system.** See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before relying on
it for anything real.

## Current status

**All 6 milestones are complete.** See
[`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md) for the
authoritative summary of what was built, what was explicitly deferred, and
real measured test/benchmark results — this README covers setup and
day-to-day usage; that report is the honest final accounting. **The weapon
detector and aggressive-motion heuristic have real, measured,
honestly-modest accuracy** — see `docs/MODEL_REGISTRY.md` before relying
on either for anything beyond a demo.

## Architecture

```
CCTV/IP Camera or Video File
        │  FFmpeg/OpenCV ingest (implemented)
        ▼
Bounded Frame Queue → Object Detector → Per-Camera Tracker   (implemented)
        │
        ▼
Rule Engine (zones, abandoned objects, weapon, aggressive motion)   (implemented)
        │
        ▼
Incident Service → PostgreSQL + Local Evidence Storage        (implemented)
        │                                  │
        ▼                                  ▼
Notification Worker (email/in-app)   Dashboard (React: live feed,
  (implemented)                       incidents, analytics, settings)
```

- **Backend** (`backend/`): FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL.
  Cookie-based JWT auth, role-based access control (admin/operator/viewer).
- **Frontend** (`frontend/`): React 19 + TypeScript + Vite + Tailwind CSS 4
  + TanStack Query + React Router + Recharts.
- **Vision worker** (`vision_worker/`): OpenCV/FFmpeg ingest, detectors
  (RF-DETR Nano default / YOLO opt-in adapter), an IoU-based per-camera
  tracker, frame annotation, and a rule engine (zone intrusion with
  dwell-time/cooldown, abandoned-object detection with stationarity/owner-
  proximity checks). Runs in-process inside the backend container (two
  threads per active camera), not as a separate microservice, per the
  brief's "avoid microservices for their own sake" guidance.
- **Deployment**: Docker Compose (PostgreSQL + backend + Caddy serving the
  built frontend and reverse-proxying `/api`), with a documented
  non-Docker dev setup below.

Tracking is per-camera only — there is no cross-camera identity matching,
by design (see `docs/LIMITATIONS.md`).

## Quick start (Docker Compose)

Requires Docker Engine and Docker Compose on Ubuntu (or any Linux/macOS
host with Docker installed).

```bash
git clone <this-repo-url> smartvision
cd smartvision
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and SECRET_KEY to real random values.
# Generate them with:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
```

For local evaluation (not a real deployment), also set in `.env`:

```
ALLOW_DEV_BOOTSTRAP=true
```

Then:

```bash
docker compose up -d --build
```

This starts three containers: `postgres`, `backend` (runs Alembic
migrations automatically on startup, then serves the API on
`127.0.0.1:8000`), and `web` (Caddy, serving the built frontend and
proxying `/api/*` to the backend, on `localhost:8080`).

Create the first admin account:

```bash
# If ALLOW_DEV_BOOTSTRAP=true, from your host machine:
curl -X POST http://localhost:8080/api/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","full_name":"Your Name","password":"a-strong-password-10+chars"}'

# Otherwise (production posture), use the interactive CLI instead:
docker compose exec backend python scripts/create_admin.py
```

Open **http://localhost:8080** and log in.

### Enable an object detector and add a camera

Fresh installs have no object detector enabled — camera feeds show raw
video with no detection overlay until you run:

```bash
# Apache-2.0 default (RF-DETR Nano) -- always attempted:
docker compose exec backend python scripts/download_models.py

# To also enable the opt-in AGPL-3.0 YOLO adapter:
docker compose exec backend python scripts/download_models.py --enable-yolo-agpl
```

Then restart the backend so running camera workers pick up the change:
`docker compose restart backend`. Add a camera from the **Cameras** page in
the dashboard — a video-file source pointing at a file under `sample_data/`
works without any real camera hardware.

### Windows USB webcam with Docker Desktop

Run the camera bridge on Windows so the Linux backend can read your webcam.
It uses a private token and listens on localhost. One bridge discovers all
Windows cameras by name and opens only cameras selected in SmartVision.

From the repository root in PowerShell (Python 3.12 or newer):

```powershell
# Only needed if your Windows Python does not already have OpenCV:
py -3 -m pip install opencv-python-headless
py -3 -m pip install --target .usb-camera/packages -r scripts/usb_camera_requirements.txt

py -3 scripts/usb_camera_bridge.py --configure-docker
```

Leave that terminal running. The bridge updates only `USB_CAMERA_BRIDGE_URL`
in the root `.env`; its token is stored in the gitignored `.usb-camera/` directory.
If your existing backend already downloaded detector weights, preserve
them before recreating the container (skip this on a fresh installation):

```powershell
New-Item -ItemType Directory -Force models/rfdetr | Out-Null
docker compose cp backend:/root/.roboflow/models/. ./models/rfdetr
```

In another terminal, apply the backend setting and adapter to your existing
backend image without rebuilding the AI dependencies, and build the device picker:

```powershell
npm --prefix frontend install
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.usb.yml up -d --no-build --no-deps backend web
```

Open **Cameras → Add camera → USB webcam** and select the actual device
name. To switch an existing USB entry, use **Change device → Use camera**.
The list refreshes every five seconds while the picker is open; **Refresh
devices** scans immediately. Then open **Live Monitoring**.

Newly connected cameras appear without restarting the bridge. The bridge
remembers device identities in `.usb-camera/devices.json`, so unplugging
a selected camera does not silently switch to the laptop camera when
Windows renumbers devices. Reconnecting the same device lets the backend
retry automatically. Moving it to a different USB port may require selecting
it again if Windows assigns a new device path.

To list devices without opening them: `py -3 scripts/usb_camera_bridge.py --list`.
Windows must recognize a compatible camera driver; the bridge cannot make
an undetected or disconnected device available.
On Windows it tries Media Foundation first (including DroidCam), then
DirectShow for the same device if needed. For a DroidCam phone, connect
the phone in the DroidCam Windows client first, then select **DroidCam Video**.
Close other camera apps and enable Windows camera access for desktop apps
if the bridge cannot open the device. After restarting Windows, run the
bridge command again. Ctrl+C stops webcam sharing.

Use the same two Compose files for subsequent `up` commands while using
this local override. It mounts the camera API/adapter and the built frontend.
After full backend and frontend image builds, the override is unnecessary.

Leave `USB_CAMERA_BRIDGE_URL` unset for a backend that opens a USB device
directly. Docker detector weights now persist under `models/rfdetr/`.

### Phone cameras using HTTP / MJPEG

For the Android IP Webcam app, choose **HTTP / MJPEG stream** in **Cameras**
and enter the direct video URL, for example `http://192.168.1.19:8080/video`.
The address without `/video` is the camera's web-control page, not its video.
Keep the phone's camera server running and reachable from the backend.
Use **RTSP stream** only for URLs beginning with `rtsp://` or `rtsps://`.
Paste the plain URL, without Markdown link brackets.

### Enable email notifications (optional)

Without SMTP configured, incidents still create in-app notifications and
the rest of the app works normally — email notifications are simply
marked "skipped, not configured" (visible in Settings → Audit Log and via
`GET /api/notifications`). To enable real email delivery, set in `.env`:

```
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_FROM_ADDRESS=alerts@yourdomain.com
```

Then restart the backend. Every admin user gets an email for each new
incident; admins and operators both get an in-app notification. A
background worker polls for pending emails every 15 seconds and retries
failed deliveries with exponential backoff (1m, 5m, 15m, 1h, 4h) up to 6
attempts before giving up.

### Train and enable the weapon detector (optional)

There is no pretrained weapon-detection checkpoint to download — it has to
be trained. The full pipeline (real, tested, and already run once against
a real dataset — see `docs/MODEL_REGISTRY.md` for the actual measured
results):

```bash
cd backend && uv sync --extra yolo   # needed for both training and inference

python ../scripts/weapon_detection/prepare_dataset.py \
  --source-dir /path/to/OD-WeaponDetection/Sohas_weapon-Detection-YOLOv5 \
  --output-dir /path/to/prepared-data

python ../scripts/weapon_detection/train.py \
  --dataset /path/to/prepared-data/dataset.yaml \
  --output-dir /path/to/model-output --epochs 50   # 3 was used for pipeline validation only

python ../scripts/weapon_detection/evaluate.py \
  --checkpoint /path/to/model-output/train/weights/best.pt \
  --dataset /path/to/prepared-data/dataset.yaml --split test

python ../scripts/weapon_detection/export_onnx.py \
  --checkpoint /path/to/model-output/train/weights/best.pt

python ../scripts/download_models.py \
  --enable-weapon-detector /path/to/model-output/train/weights/best.onnx
```

The dataset itself comes from `github.com/ari-dasci/OD-WeaponDetection`
(CC BY-SA 4.0) — see that repository for how to download it.

To stop: `docker compose down` (add `-v` to also delete the Postgres
volume and evidence storage).

### Faster backend rebuilds

After backend code changes, rebuild only that service:

```bash
docker compose up -d --build --no-deps backend
```

The backend Dockerfile caches system packages and third-party Python/AI
dependencies separately from application code. Dependency installation is
repeated when dependency manifests or the lockfile change; a BuildKit cache
also retains downloaded packages. The first build with this layout populates
the cache. Avoid `--no-cache` and build-cache pruning when you want fast rebuilds.

If no code changed, start existing images with `docker compose up -d --no-build`,
or restart an already-created backend with `docker compose restart backend`.
Restarting alone does not include code changes in the image.

## Non-Docker development setup

Requires Python 3.12, Node.js 20+, PostgreSQL 16 (or point `DATABASE_URL`
at any reachable Postgres instance), and [`uv`](https://docs.astral.sh/uv/).

### Backend

```bash
cd backend
uv sync                      # installs exactly what's pinned in uv.lock
cp ../.env.example ../.env   # or export the variables below directly

# Point at your local Postgres (adjust user/password/db as needed):
export DATABASE_URL="postgresql+psycopg://smartvision:smartvision@localhost:5432/smartvision"
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export ALLOW_DEV_BOOTSTRAP=true

uv run alembic upgrade head
uv run python ../scripts/download_models.py   # optional: enable an object detector
uv run uvicorn app.main:app --reload --port 8000
```

To also install the opt-in AGPL-3.0 YOLO adapter or the RF-DETR Nano
extras (needed before `download_models.py` can actually download either
checkpoint):

```bash
uv sync --extra yolo     # ultralytics + torch (AGPL-3.0 -- opt-in)
uv sync --extra rfdetr   # rfdetr + torch (Apache-2.0 -- the default)
```

Run the test suite (uses an isolated SQLite database per test, no Postgres
required):

```bash
uv run pytest -v
```

The vision pipeline (detectors, tracker, camera ingest) has its own test
suite, runnable from the same environment since it's installed as an
editable dependency:

```bash
uv run --with pytest pytest ../vision_worker/tests/ -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` by default
(see `vite.config.ts`); set `VITE_API_PROXY_TARGET` to override. Open
**http://localhost:5173**.

## API documentation

Interactive OpenAPI docs are served by FastAPI at `/docs` (Swagger UI) and
`/redoc` on the backend (`http://localhost:8000/docs` in dev, or
`http://localhost:8080/api/docs`... note: currently only exposed on the
backend's own port, not yet proxied — see Milestone 2 for the full
API surface).

### Sample requests

**Health check** (no auth required):

```bash
curl http://localhost:8000/api/health
```

```json
{"status":"ok","uptime_seconds":42.1,"database":{"connected":true,"error":null}}
```

**Login** (sets an HttpOnly session cookie):

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"your-password"}'
```

**Get current user** (using the cookie from login):

```bash
curl -b cookies.txt http://localhost:8000/api/auth/me
```

```json
{"id":"...","email":"admin@example.com","full_name":"Your Name","role":"admin","is_active":true,"created_at":"..."}
```

**Add a camera** (admin only) and check its live health:

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/cameras \
  -H "Content-Type: application/json" \
  -d '{"name":"Front Entrance","source_type":"file","source_uri":"synthetic_pipeline_test.mp4","inference_fps":5}'

curl -b cookies.txt http://localhost:8000/api/cameras/<camera-id>/health
```

```json
{"camera_id":"...","connected":true,"last_frame_at":"...","last_error":null,"measured_capture_fps":4.8,"consecutive_reconnect_attempts":0,"active_track_count":3}
```

The live annotated feed is at `GET /api/cameras/<camera-id>/stream.mjpg`
(MJPEG, viewable directly in a browser or an `<img>` tag).

**Draw a restricted zone** (normalized polygon coordinates) and review the
resulting incidents once someone dwells in it:

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/zones \
  -H "Content-Type: application/json" \
  -d '{"camera_id":"<camera-id>","name":"Loading Dock","polygon":[[0.5,0.0],[1.0,0.0],[1.0,1.0],[0.5,1.0]],"dwell_time_seconds":2,"severity":"high"}'

curl -b cookies.txt "http://localhost:8000/api/incidents?status=new"

curl -b cookies.txt -X PATCH http://localhost:8000/api/incidents/<incident-id> \
  -H "Content-Type: application/json" \
  -d '{"status":"acknowledged"}'
```

The evidence snapshot for any incident is at
`GET /api/incidents/<incident-id>/snapshot`.

## Project structure

```
smartvision/
├── backend/          FastAPI app, SQLAlchemy models, Alembic migrations, tests
├── frontend/          React + TypeScript + Vite dashboard
├── vision_worker/     Detectors, trackers, rule engines (Milestone 2+)
├── docker/             Caddyfile (reverse proxy + static frontend)
├── docs/               Limitations, production setup, model registry
├── scripts/            create_admin.py, and (later) model download/benchmark scripts
├── evidence_storage/   Local filesystem evidence storage (gitignored contents)
├── sample_data/        Demo video clips for Demo Mode (Milestone 6)
├── docker-compose.yml
└── .env.example
```

## Implementation status

- [x] **Milestone 1 — Foundation**: repo structure, Docker Compose,
      PostgreSQL + Alembic migrations (tested against real Postgres, not
      just SQLite), FastAPI backend with cookie-based JWT auth and RBAC,
      login rate limiting, audit logging, React/TS/Vite/Tailwind frontend
      shell with a working login flow, full navigation IA with honest
      "not yet implemented" states, 15 passing backend tests.
- [x] **Milestone 2 — Video pipeline**: camera ingest (RTSP/file/USB) with
      reconnect/backoff and credential-scrubbed logging; a detector
      abstraction with a real RF-DETR Nano adapter (Apache-2.0 default,
      code-complete but unverified in this dev sandbox — see
      `docs/LIMITATIONS.md`) and a real, fully-verified opt-in YOLO adapter
      (AGPL-3.0, disabled by default); an IoU-based per-camera tracker;
      live annotated MJPEG streaming; camera CRUD API with RBAC and SSRF
      protections; a model registry with an explicit, non-HTTP enable flow
      (`scripts/download_models.py`). 26 backend + 30 vision-worker tests
      passing, including one real end-to-end inference run.
- [x] **Milestone 3 — Reliable incidents**: zone editor (click-to-draw
      polygons over the live feed) with point-in-polygon intrusion
      detection, dwell-time, and cooldown logic; abandoned-object detection
      with stationarity and owner-proximity checks; a rule engine wired
      into the live camera pipeline via a tested callback mechanism; real,
      persisted incidents with saved JPEG evidence snapshots and a
      database-level dedup safety net; a full incident review API and UI
      (acknowledge/resolve/false-positive, notes, audit timeline). Verified
      live end-to-end: a real tracked person dwelling in a real configured
      zone produced a real incident with a real saved snapshot. 61
      vision-worker + 48 backend tests passing (109 total across the
      project), ruff/mypy clean.
- [x] **Milestone 4 — Advanced AI**: real weapon detector, fine-tuned and
      evaluated on the Sohas dataset (`ari-dasci/OD-WeaponDetection`,
      CC BY-SA 4.0) with a full reproducible pipeline
      (`scripts/weapon_detection/`: prepare dataset → train → evaluate →
      export ONNX), verified live end-to-end against real Postgres and a
      real image; an aggressive-motion heuristic (no validated fight
      classifier exists, so per the brief's own fallback this labels
      candidates "Aggressive motion — review required", never "Fight
      confirmed"); a weapon temporal-confirmation rule requiring several
      consecutive frames before alerting. Both new detection categories'
      real, measured accuracy limitations are documented in
      `docs/MODEL_REGISTRY.md` rather than glossed over. 48 backend + 87
      vision-worker tests passing, ruff/mypy clean.
- [x] **Milestone 5 — Operations**: database-backed outbox notification
      system with real SMTP email sending, retry with exponential backoff,
      deduplication, and a background asyncio worker (all polled, no
      external queue service); in-app notifications with read/unread
      state; real analytics computed from actual incident records (daily
      trend, category/severity/camera breakdowns, response time — an empty
      deployment correctly shows all zeros, never synthetic example data);
      user management (create, deactivate/reactivate, role assignment) and
      a full audit log viewer, both admin-only. Verified live end-to-end:
      a real triggered incident produced real notifications, correctly
      marked "skipped, SMTP not configured" by the actual background
      worker. Caught and fixed a real bug along the way -- Python's dict()
      constructor misinterprets a SQLAlchemy Result's .keys() method as
      mapping-like, breaking column-pair aggregation queries; mypy's
      strictness surfaced it, the fix was verified against real data, not
      just the type checker. 78 backend + 87 vision-worker tests passing,
      ruff/mypy clean.
- [x] **Milestone 6 — Verification**: `scripts/benchmark.py` produced real,
      measured detector latency/FPS/memory and multi-camera pipeline
      throughput on this project's actual development hardware (1 CPU
      core) — see `docs/benchmark_report.json` and
      `docs/IMPLEMENTATION_REPORT.md`. Demo Mode (`/api/demo` +
      dashboard page) launches a clearly-labeled sample-video camera,
      verified live end-to-end. Full test suite: 85 backend + 87
      vision-worker tests passing (172 total), ruff/mypy clean on both
      packages. `docs/IMPLEMENTATION_REPORT.md` is the final,
      authoritative accounting of completed vs. deferred features and
      measured results.

## Demo Mode

From the dashboard's **Demo Mode** page (admin only), pick a sample clip
and click "Launch demo" — this creates a real camera against that file,
clearly labeled `DEMO MODE` in its notes, and runs the exact same
detection pipeline as any other camera. It's the same code path as a
regular file-source camera; nothing about detections shown in demo mode is
simulated or scripted.

## Benchmarking

`scripts/benchmark.py` measures real detector latency/FPS/memory and real
multi-camera pipeline throughput on whatever machine you run it on:

```bash
cd backend && uv sync --extra yolo   # if not already installed
python ../scripts/benchmark.py --camera-counts 1 2 4
```

Results are specific to your hardware and are written to
`docs/benchmark_report.json` — see `docs/IMPLEMENTATION_REPORT.md` for the
numbers measured on this project's own (1-CPU-core) development machine,
and don't assume they transfer to different hardware.

## Troubleshooting

- **`docker compose up` fails at the backend with a database connection
  error**: the backend's entrypoint waits up to 60 seconds for Postgres to
  accept connections before running migrations. Check `docker compose logs
  postgres` if it still fails after that.
- **`bootstrap-admin` returns 403**: `ALLOW_DEV_BOOTSTRAP` is `false` (the
  default). Use `scripts/create_admin.py` instead (see
  [Production Setup](docs/PRODUCTION_SETUP.md)), or set
  `ALLOW_DEV_BOOTSTRAP=true` for local evaluation only.
- **`bootstrap-admin` returns 409**: a user already exists. This endpoint
  only works on a database with zero users, by design.
- **Frontend shows "Could not reach the API"**: confirm the backend
  container/process is running and, in dev, that `VITE_API_PROXY_TARGET`
  (or the default `http://localhost:8000`) matches where it's listening.
