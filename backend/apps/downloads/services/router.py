from __future__ import annotations

import logging
from pathlib import Path

from apps.downloads.services.base import DownloadResult, ProgressCallback
from apps.downloads.services.classify import classify_url
from apps.downloads.services.direct import download_direct
from apps.downloads.services.media import finalize_video, is_video_file
from apps.downloads.services.ytdlp import download_ytdlp

logger = logging.getLogger(__name__)

__all__ = ["classify_url", "download_url"]


def download_url(
    url: str,
    dest_dir: Path,
    *,
    source_type: str | None = None,
    preferred_format: str = "best",
    max_bytes: int,
    progress_callback: ProgressCallback = None,
    clip_range_ms: tuple[int, int] | None = None,
) -> DownloadResult:
    kind = source_type or classify_url(url)

    if kind == "direct":
        result = download_direct(
            url,
            dest_dir,
            max_bytes=max_bytes,
            progress_callback=progress_callback,
            clip_range_ms=clip_range_ms,
        )
    else:
        try:
            result = download_ytdlp(
                url,
                dest_dir,
                preferred_format=preferred_format,
                max_bytes=max_bytes,
                progress_callback=progress_callback,
                clip_range_ms=clip_range_ms,
            )
        except Exception as ytdlp_exc:
            # HTML watch pages are not a valid fallback for extractor URLs.
            logger.warning("yt-dlp failed for %s (%s)", url, ytdlp_exc)
            raise

    if is_video_file(Path(result.file_path), result.mime_type):
        try:
            extra = finalize_video(Path(result.file_path), dest_dir)
        except Exception:  # noqa: BLE001
            logger.exception("video post-processing failed for %s", result.file_path)
        else:
            result.file_path = extra["file_path"]
            result.width = extra["width"]
            result.height = extra["height"]
            result.duration = extra["duration"]
            result.thumbnail_path = extra["thumbnail_path"]

    return result
