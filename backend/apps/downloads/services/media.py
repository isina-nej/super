"""ffmpeg/ffprobe-based post-processing: thumbnails, streaming-ready MP4s, clipping.

Pure media plumbing (no Telegram/aiogram, no Django models) — kept in line with
the modular boundary enforced by scripts/validate.py.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from apps.downloads.services.base import DownloadError

logger = logging.getLogger(__name__)

# Containers where moving the moov atom to the front ("faststart") matters.
# WebM/Matroska don't use moov atoms, so they're left alone.
_FASTSTART_EXTS = {".mp4", ".mov", ".m4v"}
_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}

_FFPROBE_TIMEOUT = 60
_FFMPEG_REMUX_TIMEOUT = 900


def is_video_file(path: Path, mime_type: str = "") -> bool:
    if (mime_type or "").startswith("video/"):
        return True
    return path.suffix.lower() in _VIDEO_EXTS


def probe_media(path: Path) -> dict:
    """Return {width, height, duration} (seconds) via ffprobe, best-effort."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_FFPROBE_TIMEOUT, check=False)
        data = json.loads(proc.stdout or b"{}")
    except Exception:  # noqa: BLE001
        logger.warning("ffprobe failed for %s", path, exc_info=True)
        return {}

    streams = data.get("streams") or [{}]
    stream = streams[0] if streams else {}
    fmt = data.get("format") or {}
    try:
        duration = int(float(fmt.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0
    try:
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    return {"width": width, "height": height, "duration": duration}


def ensure_faststart(path: Path) -> Path:
    """Remux MP4/MOV so the moov atom is at the front (needed for streaming
    playback in Telegram clients while the file is still being downloaded).

    Uses stream copy (no re-encode), so it's fast even for large files.
    Falls back to the original file if ffmpeg fails for any reason.
    """
    if path.suffix.lower() not in _FASTSTART_EXTS:
        return path

    tmp = path.with_name(f"{path.stem}.faststart{path.suffix}")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_FFMPEG_REMUX_TIMEOUT, check=False)
    except Exception:  # noqa: BLE001
        logger.warning("faststart remux crashed for %s", path, exc_info=True)
        tmp.unlink(missing_ok=True)
        return path

    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        logger.warning(
            "faststart remux failed for %s: %s",
            path,
            proc.stderr.decode(errors="ignore")[-500:],
        )
        tmp.unlink(missing_ok=True)
        return path

    tmp.replace(path)
    return path


def generate_thumbnail(path: Path, dest_dir: Path, duration: int = 0) -> Path | None:
    """Extract a JPEG cover frame for Telegram (<=320px side, small file size)."""
    thumb_path = dest_dir / "thumbnail.jpg"
    seek = min(3.0, duration / 2) if duration else 0.5
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seek:.2f}",
        "-i", str(path),
        "-frames:v", "1",
        "-vf", "scale=320:-2",
        "-q:v", "4",
        str(thumb_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_FFPROBE_TIMEOUT, check=False)
    except Exception:  # noqa: BLE001
        logger.warning("thumbnail generation crashed for %s", path, exc_info=True)
        return None

    if proc.returncode != 0 or not thumb_path.is_file() or thumb_path.stat().st_size == 0:
        logger.warning(
            "thumbnail generation failed for %s: %s",
            path,
            proc.stderr.decode(errors="ignore")[-500:],
        )
        thumb_path.unlink(missing_ok=True)
        return None
    return thumb_path


def trim_media_file(path: Path, start_ms: int, end_ms: int) -> Path:
    """Cut [start_ms, end_ms) out of a local media file in place (stream copy).

    Raises DownloadError if ffmpeg fails. Used for sources that have no
    native "download only this range" support (i.e. direct HTTP files).
    """
    start_s = max(0, start_ms) / 1000
    duration_s = max(0.05, (end_ms - start_ms) / 1000)
    tmp = path.with_name(f"{path.stem}.clip{path.suffix}")
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-i", str(path),
        "-t", f"{duration_s:.3f}",
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_FFMPEG_REMUX_TIMEOUT, check=False)
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"برش ویدیو ناموفق بود: {exc}") from exc

    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            f"برش ویدیو ناموفق بود: {proc.stderr.decode(errors='ignore')[-300:]}"
        )
    tmp.replace(path)
    return path


def finalize_video(file_path: Path, dest_dir: Path) -> dict:
    """Run faststart + probe + thumbnail for a downloaded video.

    Always best-effort beyond the file existing: failures degrade gracefully
    (video still gets delivered, just without a thumbnail/streaming flag).
    """
    path = ensure_faststart(file_path)
    info = probe_media(path)
    thumb = generate_thumbnail(path, dest_dir, duration=info.get("duration", 0))
    return {
        "file_path": str(path),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "duration": info.get("duration", 0),
        "thumbnail_path": str(thumb) if thumb else "",
    }
