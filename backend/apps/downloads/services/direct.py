from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from apps.downloads.services.base import (
    DownloadError,
    DownloadResult,
    FileTooLargeError,
    ProgressCallback,
)
from apps.downloads.services.media import trim_media_file

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 256


def _filename_from_headers(url: str, content_disposition: str | None) -> str:
    if content_disposition:
        match = re.search(
            r"filename\*=UTF-8''([^;]+)|filename=\"([^\"]+)\"|filename=([^;]+)",
            content_disposition,
            flags=re.IGNORECASE,
        )
        if match:
            name = next(g for g in match.groups() if g)
            return Path(unquote(name.strip().strip("'"))).name
    path_name = Path(unquote(urlparse(url).path)).name
    return path_name or "download.bin"


def download_direct(
    url: str,
    dest_dir: Path,
    *,
    max_bytes: int,
    progress_callback: ProgressCallback = None,
    timeout: float = 600.0,
    clip_range_ms: tuple[int, int] | None = None,
) -> DownloadResult:
    dest_dir.mkdir(parents=True, exist_ok=True)

    with httpx.stream(
        "GET",
        url,
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "TelegramDownloadBot/1.0"},
    ) as response:
        if response.status_code >= 400:
            raise DownloadError(f"HTTP {response.status_code} هنگام دانلود مستقیم.")

        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            declared = int(content_length)
            if declared > max_bytes:
                raise FileTooLargeError(declared, max_bytes)

        filename = _filename_from_headers(url, response.headers.get("Content-Disposition"))
        # Sanitize path traversal
        filename = Path(filename).name or "download.bin"
        dest = dest_dir / filename

        mime = response.headers.get("Content-Type", "").split(";")[0].strip()
        if not mime:
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        written = 0
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise FileTooLargeError(written, max_bytes)
                fh.write(chunk)
                if progress_callback:
                    if content_length and str(content_length).isdigit() and int(content_length) > 0:
                        progress_callback(min(99, int(written * 100 / int(content_length))))
                    else:
                        progress_callback(1)

    if clip_range_ms:
        start_ms, end_ms = clip_range_ms
        dest = trim_media_file(dest, start_ms, end_ms)

    if progress_callback:
        progress_callback(100)

    return DownloadResult(
        file_path=str(dest),
        source_type="direct",
        title=filename,
        mime_type=mime,
        file_size=dest.stat().st_size,
    )
