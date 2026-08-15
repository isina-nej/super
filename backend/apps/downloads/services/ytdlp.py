from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil
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


def _is_pornhub(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "pornhub.com" in host or host.endswith("pornhub.org")


def _is_twitter(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"x.com", "www.x.com", "mobile.x.com"} or host.endswith("twitter.com")


def _normalize_media_url(url: str) -> str:
    """Strip /video/1 suffixes so the Twitter extractor sees a status URL."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if _is_twitter(url):
        match = re.match(r"(/.*/status/\d+)", path)
        if match:
            path = match.group(1)
        return urlunparse(("https", "x.com", path, "", "", ""))
    return url


def _urls_to_try(url: str) -> list[str]:
    ordered = [url, _normalize_media_url(url)]
    fallback = _pornhub_fallback_url(url)
    if fallback:
        ordered.append(fallback)
    seen: list[str] = []
    for item in ordered:
        if item and item not in seen:
            seen.append(item)
    return seen


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def format_selector_for(url: str, preferred_format: str) -> str:
    if preferred_format == "audio":
        return "bestaudio/best"
    if preferred_format in {"best", ""}:
        if _is_pornhub(url) or _is_twitter(url):
            # Progressive HTTP can use multi-connection; HLS remains the fallback.
            return "best[ext=mp4][protocol^=http]/b[protocol^=http]/b/bv*+ba/best"
        return "b/bv*+ba/best"
    return f"{preferred_format}/b/best"


def _download_speed_opts() -> dict:
    """Parallel HLS fragments + aria2c multi-connection for progressive HTTP."""
    connections = str(_int_env("YTDLP_ARIA2_CONNECTIONS", 16, lo=2, hi=32))
    opts: dict = {
        "concurrent_fragment_downloads": _int_env("YTDLP_CONCURRENT_FRAGMENTS", 16, lo=1, hi=32),
        "retries": 10,
        "fragment_retries": 10,
        "buffersize": 1024 * 1024,
        "http_chunk_size": 10 * 1024 * 1024,
    }
    if shutil.which("aria2c"):
        opts["external_downloader"] = {"http": "aria2c", "https": "aria2c"}
        opts["external_downloader_args"] = {
            "aria2c": [
                "-x",
                connections,
                "-s",
                connections,
                "-k",
                "1M",
                "--file-allocation=none",
                "--summary-interval=0",
                "--min-split-size=1M",
                "--max-tries=8",
                "--retry-wait=1",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
            ]
        }
        logger.info("yt-dlp using aria2c with %s connections", connections)
    else:
        logger.info("aria2c not found; using native downloader with concurrent fragments")
    return opts


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


def _has_video_track(fmt: dict) -> bool:
    vcodec = fmt.get("vcodec")
    if vcodec in (None, ""):
        return bool(fmt.get("height") or fmt.get("width"))
    return vcodec != "none"


def _has_audio_track(fmt: dict) -> bool:
    acodec = fmt.get("acodec")
    if acodec in (None, ""):
        proto = str(fmt.get("protocol") or "")
        return proto.startswith("http") and "m3u8" not in proto
    return acodec != "none"


def _format_rank(fmt: dict, *, has_audio: bool, fmt_id: str) -> tuple[int, int, int]:
    proto = str(fmt.get("protocol") or "")
    progressive = int(proto.startswith("http") and "m3u8" not in proto)
    combined = int(has_audio and "+" not in fmt_id)
    size = int(fmt.get("filesize") or fmt.get("filesize_approx") or 0)
    return (progressive, combined, size)


def _size_label(fmt: dict) -> str:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    try:
        size_n = int(size)
    except (TypeError, ValueError):
        return ""
    if size_n <= 0:
        return ""
    if size_n >= 1024**3:
        return f" {size_n / 1024**3:.1f}GB"
    return f" {max(1, size_n // (1024 * 1024))}MB"


def compact_format_choices(info: dict) -> list[dict]:
    """Collapse yt-dlp formats into unique height / audio buttons."""
    by_height: dict[int, dict] = {}
    ranks: dict[int, tuple[int, int, int]] = {}
    for fmt in info.get("formats") or []:
        if (fmt.get("ext") or "") == "mhtml":
            continue
        fid = str(fmt.get("format_id") or "")
        if not fid:
            continue
        height = int(fmt.get("height") or 0)
        has_v = _has_video_track(fmt)
        has_a = _has_audio_track(fmt)
        if not has_v or height < 144:
            continue
        fmt_id = fid if has_a else f"{fid}+bestaudio"
        rank = _format_rank(fmt, has_audio=has_a, fmt_id=fmt_id)
        prev = by_height.get(height)
        if prev is not None and ranks.get(height, (0, 0, 0)) >= rank:
            continue
        note = (fmt.get("format_note") or "").strip()
        extra = f" {note}" if note and note not in {f"{height}p", str(height)} else ""
        by_height[height] = {
            "id": fmt_id[:60],
            "label": f"{height}p{extra}{_size_label(fmt)}"[:32],
            "height": height,
            "ext": fmt.get("ext") or "mp4",
        }
        ranks[height] = rank
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

    url = _normalize_media_url(url)
    opts = _base_ydl_opts(url)
    opts["skip_download"] = True
    last_exc: BaseException | None = None
    urls_to_try = _urls_to_try(url)
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

    url = _normalize_media_url(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(title).200B [%(id)s].%(ext)s")

    postprocessors: list[dict] = []
    format_selector = format_selector_for(url, preferred_format)
    if preferred_format == "audio":
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

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
    ydl_opts.update(_download_speed_opts())
    ydl_opts.update(
        {
            "outtmpl": outtmpl,
            "format": format_selector,
            "progress_hooks": [_hook],
            "postprocessors": postprocessors,
            "restrictfilenames": True,
        }
    )
    urls_to_try = _urls_to_try(url)

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
