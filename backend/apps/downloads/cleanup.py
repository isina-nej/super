from __future__ import annotations

import logging
import shutil
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def cleanup_job_file(file_path: str) -> None:
    """Delete a downloaded file and its job directory if empty."""
    if not file_path:
        return

    path = Path(file_path)
    media_root = Path(settings.MEDIA_ROOT).resolve()

    try:
        resolved = path.resolve()
    except OSError:
        return

    # Safety: only delete under MEDIA_ROOT
    try:
        resolved.relative_to(media_root)
    except ValueError:
        logger.warning("Refusing to delete path outside MEDIA_ROOT: %s", resolved)
        return

    if resolved.is_file():
        try:
            resolved.unlink()
        except OSError as exc:
            logger.warning("Failed to delete %s: %s", resolved, exc)

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
