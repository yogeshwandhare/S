"""Resolve camera video sources stored in sample_data or uploaded storage."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

def resolve_video_source(source_uri: str) -> str:
    """Resolve a database FILE URI to an allowed on-disk video location."""
    if source_uri.startswith("uploads/"):
        filename = source_uri.removeprefix("uploads/")
        if not filename or Path(filename).name != filename:
            raise ValueError("Invalid uploaded video path")
        return str(Path(get_settings().EVIDENCE_STORAGE_DIR) / "camera_uploads" / filename)

    sample_dir = Path(get_settings().SAMPLE_DATA_DIR).resolve()
    sample_path = (sample_dir / source_uri).resolve()
    if not sample_path.is_relative_to(sample_dir):
        raise ValueError("Invalid sample video path")
    return str(sample_path)
