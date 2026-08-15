from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from apps.downloads.services.base import (
    DownloadError,
    DownloadResult,
    FileTooLargeError,
    ProgressCallback,
)

logger = logging.getLogger(__name__)


def download_ytdlp(
    url: str,
    dest_dir: Path,
    *,
    preferred_format: str = "best",
    max_bytes: int,
    progress_callback: ProgressCallback = None,
) -> DownloadResult:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError("yt-dlp نصب نشده است.") from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(title).200B [%(id)s].%(ext)s")

    if preferred_format == "audio":
        format_selector = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        format_selector = "bv*+ba/b"
        postprocessors = []

    def _hook(d: dict) -> None:
        if not progress_callback:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            if total and total > max_bytes:
                raise FileTooLargeError(int(total), max_bytes)
            if total:
                progress_callback(min(99, int(downloaded * 100 / total)))
        elif d.get("status") == "finished":
            progress_callback(99)

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": format_selector,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_hook],
        "postprocessors": postprocessors,
        "restrictfilenames": True,
        "retries": 3,
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("اطلاعات ویدیو دریافت نشد.")
            # After postprocessors, resolve final path
            if "requested_downloads" in info and info["requested_downloads"]:
                filepath = info["requested_downloads"][0].get("filepath")
            else:
                filepath = ydl.prepare_filename(info)
                if preferred_format == "audio":
                    filepath = str(Path(filepath).with_suffix(".mp3"))

            title = info.get("title") or Path(filepath).stem
    except FileTooLargeError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("yt-dlp failed for %s", url)
        raise DownloadError(f"خطا در yt-dlp: {exc}") from exc

    path = Path(filepath)
    if not path.exists():
        # Fallback: pick newest file in dest_dir
        candidates = sorted(dest_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        files = [p for p in candidates if p.is_file()]
        if not files:
            raise DownloadError("فایل خروجی yt-dlp پیدا نشد.")
        path = files[0]

    size = path.stat().st_size
    if size > max_bytes:
        path.unlink(missing_ok=True)
        raise FileTooLargeError(size, max_bytes)

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if progress_callback:
        progress_callback(100)

    return DownloadResult(
        file_path=str(path),
        source_type="ytdlp",
        title=str(title)[:512],
        mime_type=mime,
        file_size=size,
    )
