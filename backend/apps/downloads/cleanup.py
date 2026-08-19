from __future__ import annotations

import logging
import shutil
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def _safe_delete(file_path: str, media_root: Path) -> Path | None:
    """Delete a single file under MEDIA_ROOT and return its resolved path."""
    if not file_path:
        return None

    path = Path(file_path)
    try:
        resolved = path.resolve()
    except OSError:
        return None

    # Safety: only delete under MEDIA_ROOT
    try:
        resolved.relative_to(media_root)
    except ValueError:
        logger.warning("Refusing to delete path outside MEDIA_ROOT: %s", resolved)
        return None

    if resolved.is_file():
        try:
            resolved.unlink()
        except OSError as exc:
            logger.warning("Failed to delete %s: %s", resolved, exc)
    return resolved


def _cleanup_parent_dir(resolved: Path, media_root: Path) -> None:
    parent = resolved.parent
    try:
        if parent.is_dir() and parent != media_root and not any(parent.iterdir()):
            parent.rmdir()
        # Also try removing jobs/<id> parent chain under media/jobs
        jobs_root = media_root / "jobs"
        if parent.parent == jobs_root and parent.is_dir():
            shutil.rmtree(parent, ignore_errors=True)
    except OSError as exc:
        logger.debug("Cleanup rmdir skipped: %s", exc)


def cleanup_job_file(file_path: str) -> None:
    """Delete a downloaded file and its job directory if empty."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    resolved = _safe_delete(file_path, media_root)
    if resolved is not None:
        _cleanup_parent_dir(resolved, media_root)


def cleanup_job_files(*file_paths: str) -> None:
    """Delete several job-related files (video + thumbnail, ...) then the
    job directory if it ended up empty."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    resolved_paths = [_safe_delete(fp, media_root) for fp in file_paths]
    for resolved in resolved_paths:
        if resolved is not None:
            _cleanup_parent_dir(resolved, media_root)
