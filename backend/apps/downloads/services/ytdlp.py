from __future__ import annotations

import logging
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from apps.downloads.services.base import (
    CancelledDownload,
    DownloadError,
    DownloadResult,
    FileTooLargeError,
    ProgressCallback,
)
from apps.downloads.services.cookies import resolve_cookiefile

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
    if "redirection detected" in lowered:
        return (
            "Pornhub از IP این سرور ویدیو را نشان نمی‌دهد (ریدایرکت به صفحه اصلی). "
            "کوکی کمکی نکرد؛ معمولاً بلاک دیتاسنتر است. "
            "برای این سایت باید پروکسی خانگی در YTDLP_PROXY بگذاری."
        )
    if "403" in text or "412" in text:
        return "سایت ویدیو دسترسی را بست. ممکن است محدودیت جغرافیایی یا ضدبات باشد."
    if "sign in" in lowered or "login required" in lowered or "age verification" in lowered or "age-gate" in lowered:
        return "این ویدیو نیاز به لاگین یا تأیید سن دارد. کوکی مرورگر را در YTDLP_COOKIES_FILE بگذارید."
    # Strip noisy Python exception wrappers for Telegram
    text = re.sub(r"\s*\(caused by <[^>]+>\)\s*", " ", text)
    return f"خطا در دانلود: {text.strip()[:400]}"


def _is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "youtube.com" in host or host.endswith("youtu.be")


def _base_ydl_opts(url: str) -> dict:
    opts: dict = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "impersonate": _impersonate_target(),
        "http_headers": {
            "User-Agent": _BROWSER_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": url,
        },
        "extractor_args": {
            "generic": {"impersonate": ["chrome"]},
            "youtube": {"player_client": ["android", "web"]},
        },
        "js_runtimes": {"node": {}},
    }
    cookiefile = resolve_cookiefile()
    if cookiefile and not _is_youtube(url):
        opts["cookiefile"] = cookiefile
    elif not _is_youtube(url):
        opts["http_headers"]["Cookie"] = "accessAgeDisclaimerPH=2"
    proxy = os.getenv("YTDLP_PROXY", "").strip()
    if proxy:
        opts["proxy"] = proxy
    return opts


def compact_format_choices(info: dict) -> list[dict]:
    """Collapse yt-dlp formats into unique height / audio buttons."""
    by_height: dict[int, dict] = {}
    for fmt in info.get("formats") or []:
        if (fmt.get("ext") or "") == "mhtml":
            continue
        fid = str(fmt.get("format_id") or "")
        if not fid:
            continue
        height = int(fmt.get("height") or 0)
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        has_v = vcodec != "none"
        has_a = acodec != "none"
        if not has_v or height < 144:
            continue
        if has_a:
            fmt_id = fid
        else:
            fmt_id = f"{fid}+bestaudio"
        prev = by_height.get(height)
        if prev is None or (has_a and "+" in str(prev.get("id") or "")):
            note = (fmt.get("format_note") or "").strip()
            extra = f" {note}" if note and note not in {f"{height}p", str(height)} else ""
            by_height[height] = {
                "id": fmt_id[:60],
                "label": f"{height}p{extra}"[:32],
                "height": height,
                "ext": fmt.get("ext") or "mp4",
            }
    rows = [by_height[h] for h in sorted(by_height, reverse=True)]
    # Keep a reasonable Telegram keyboard
    rows = rows[:8]
    rows.append({"id": "best", "label": "بهترین کیفیت", "height": 0, "ext": "mp4"})
    rows.append({"id": "audio", "label": "فقط صدا (MP3)", "height": 0, "ext": "mp3"})
    return rows


def list_ytdlp_formats(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError("yt-dlp نصب نشده است.") from exc

    opts = _base_ydl_opts(url)
    opts["skip_download"] = True
    last_exc: BaseException | None = None
    urls_to_try = [url]
    fallback = _pornhub_fallback_url(url)
    if fallback:
        urls_to_try.append(fallback)
    info = None
    for attempt_url in urls_to_try:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(attempt_url, download=False)
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("list formats failed for %s: %s", attempt_url, exc)
    if last_exc is not None or info is None:
        raise DownloadError(_friendly_ytdlp_error(last_exc or DownloadError("اطلاعات ویدیو دریافت نشد.")))
    return {
        "title": str(info.get("title") or "")[:512],
        "formats": compact_format_choices(info),
    }


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

    postprocessors: list[dict] = []
    if preferred_format == "audio":
        format_selector = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    elif preferred_format in {"best", ""}:
        format_selector = "b/bv*+ba/best"
    else:
        format_selector = f"{preferred_format}/b/best"

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
            else:
                progress_callback(1)
        elif d.get("status") == "finished":
            progress_callback(99)

    ydl_opts = _base_ydl_opts(url)
    ydl_opts.update(
        {
            "outtmpl": outtmpl,
            "format": format_selector,
            "progress_hooks": [_hook],
            "postprocessors": postprocessors,
            "restrictfilenames": True,
        }
    )
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
            except CancelledDownload:
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
    except CancelledDownload:
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
