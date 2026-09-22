# sample_data/

## synthetic_pipeline_test.mp4

A small (~400KB, 20-frame) test clip built from a single well-known,
freely-licensed test photograph (`ultralytics/assets`' `bus.jpg`, used
across the YOLO ecosystem for exactly this purpose) repeated as static
video frames.

**This is not real CCTV footage and must never be presented as such.** It
exists for two honest, narrow purposes:

1. **Automated tests** (`vision_worker/tests/test_source.py`,
   `test_worker.py`) use it to validate that file-based camera ingestion,
   detection, and tracking actually work end-to-end, without requiring
   real surveillance footage that this project has no legitimate way to
   obtain or redistribute.
2. **A no-hardware-required demo camera source** -- add a camera in the
   dashboard with source type "file" and this filename to see the live
   annotated feed without owning an IP camera or RTSP stream.

Because every frame is identical, track IDs should remain stable across
the whole clip when a working object detector is enabled -- that's a
useful sanity check in itself.

Any other video files placed in this directory are gitignored by default
(see the repo root `.gitignore`) -- this one file is a deliberate,
documented exception.
