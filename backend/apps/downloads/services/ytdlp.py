from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from apps.downloads.services.base import (
    DownloadError,
    DownloadResult,
    FileTooLargeError,
    ProgressCallback,
)

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _impersonate_target():
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget.from_str("chrome")
    except Exception:  # noqa: BLE001
        return "chrome"


def _pornhub_fallback_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"www.pornhub.com", "pornhub.com"}:
        return urlunparse(parsed._replace(netloc="cn.pornhub.com"))
    return None


def _friendly_ytdlp_error(exc: BaseException) -> str:
    text = str(exc)
    lowered = text.lower()
    if "410" in text or "gone" in lowered:
        return (
            "سایت ویدیو درخواست را مسدود کرد (HTTP 410). "
            "معمولاً به‌خاطر تشخیص سرور/بات است، نه حذف شدن ویدیو. "
            "اگر باز هم شکست خورد، لینک را در مرورگر چک کنید یا بعداً دوباره بفرستید."
        )
    if "403" in text or "412" in text:
        return "سایت ویدیو دسترسی را بست. ممکن است محدودیت جغرافیایی یا ضدبات باشد."
    if "sign in" in lowered or "login" in lowered or "age" in lowered:
        return "این ویدیو نیاز به لاگین یا تأیید سن دارد و بدون کوکی قابل دانلود نیست."
    # Strip noisy Python exception wrappers for Telegram
    text = re.sub(r"\s*\(caused by <[^>]+>\)\s*", " ", text)
    return f"خطا در دانلود: {text.strip()[:400]}"


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
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "impersonate": _impersonate_target(),
        "http_headers": {
            "User-Agent": _BROWSER_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": url,
            "Cookie": "accessAgeDisclaimerPH=2",
        },
        # PornHub age gate; ignored by other extractors
        "extractor_args": {
            "generic": {"impersonate": ["chrome"]},
        },
    }

    urls_to_try = [url]
    fallback = _pornhub_fallback_url(url)
    if fallback:
        urls_to_try.append(fallback)

    last_exc: BaseException | None = None
    info = None
    filepath = None
    title = None
    try:
        for attempt_url in urls_to_try:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(attempt_url, download=True)
                    if info is None:
                        raise DownloadError("اطلاعات ویدیو دریافت نشد.")
                    if "requested_downloads" in info and info["requested_downloads"]:
                        filepath = info["requested_downloads"][0].get("filepath")
                    else:
                        filepath = ydl.prepare_filename(info)
                        if preferred_format == "audio":
                            filepath = str(Path(filepath).with_suffix(".mp3"))
                    title = info.get("title") or Path(filepath).stem
                    last_exc = None
                    break
            except FileTooLargeError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("yt-dlp failed for %s: %s", attempt_url, exc)
                continue
        if last_exc is not None:
            raise last_exc
        if not filepath:
            raise DownloadError("اطلاعات ویدیو دریافت نشد.")

    except FileTooLargeError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("yt-dlp failed for %s", url)
        raise DownloadError(_friendly_ytdlp_error(exc)) from exc

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
