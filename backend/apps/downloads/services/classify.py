from __future__ import annotations

from urllib.parse import urlparse

# Common media hosts that yt-dlp handles well
YTDLP_HOST_HINTS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.watch",
    "vimeo.com",
    "reddit.com",
    "soundcloud.com",
    "twitch.tv",
    "bilibili.com",
    "pinterest.com",
    "vk.com",
    "ok.ru",
    "dailymotion.com",
    "rumble.com",
    "pornhub.com",
    "pornhub.org",
    "xvideos.com",
    "xnxx.com",
    "xhamster.com",
    "redtube.com",
    "youporn.com",
)

DIRECT_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".mp3",
    ".m4a",
    ".flac",
    ".wav",
    ".ogg",
    ".opus",
    ".aac",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".iso",
    ".apk",
)


def classify_url(url: str) -> str:
    """Return 'ytdlp' or 'direct' based on URL heuristics."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()

    if any(hint in host for hint in YTDLP_HOST_HINTS):
        return "ytdlp"

    if any(path.endswith(ext) for ext in DIRECT_EXTENSIONS):
        return "direct"

    # Unknown hosts without a file extension → prefer yt-dlp extractors
    return "ytdlp"
