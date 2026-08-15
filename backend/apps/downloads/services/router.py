from __future__ import annotations

import logging
from pathlib import Path

from apps.downloads.services.base import DownloadResult, ProgressCallback
from apps.downloads.services.classify import classify_url
from apps.downloads.services.direct import download_direct
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
) -> DownloadResult:
    kind = source_type or classify_url(url)

    if kind == "direct":
        return download_direct(
            url,
            dest_dir,
            max_bytes=max_bytes,
            progress_callback=progress_callback,
        )

    try:
        return download_ytdlp(
            url,
            dest_dir,
            preferred_format=preferred_format,
            max_bytes=max_bytes,
            progress_callback=progress_callback,
        )
    except Exception as ytdlp_exc:
        # HTML watch pages are not a valid fallback for extractor URLs.
        logger.warning("yt-dlp failed for %s (%s)", url, ytdlp_exc)
        raise
