from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Default: only these hosts from a full-browser JSON dump (never ship unrelated sessions).
_DEFAULT_DOMAIN_FILTERS = (
    "pornhub.com",
    "pornhub.org",
    "phncdn.com",
    "youtube.com",
    "youtu.be",
    "googlevideo.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
)


def _domain_allowed(domain: str, filters: tuple[str, ...]) -> bool:
    d = domain.lstrip(".").lower()
    if not d:
        return False
    return any(d == f or d.endswith("." + f) or f.endswith("." + d) for f in filters)


def json_cookies_to_netscape(
    cookies: list[dict],
    *,
    domain_filters: tuple[str, ...] | None = _DEFAULT_DOMAIN_FILTERS,
) -> str:
    lines = ["# Netscape HTTP Cookie File", "# Generated from JSON cookie export", ""]
    count = 0
    for item in cookies:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        name = str(item.get("name") or "")
        if not domain or not name:
            continue
        if domain_filters and not _domain_allowed(domain, domain_filters):
            continue
        host_only = bool(item.get("hostOnly"))
        flag = "FALSE" if host_only else "TRUE"
        if not host_only and not domain.startswith("."):
            domain = "." + domain
        path = str(item.get("path") or "/")
        secure = "TRUE" if item.get("secure") else "FALSE"
        expires = item.get("expirationDate")
        try:
            exp = int(float(expires)) if expires else 0
        except (TypeError, ValueError):
            exp = 0
        if item.get("session"):
            exp = 0
        value = str(item.get("value") or "")
        # Netscape is tab-separated; values must not contain tabs/newlines
        value = value.replace("\t", "").replace("\r", "").replace("\n", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{exp}\t{name}\t{value}")
        count += 1
    logger.info("Converted %s cookies to Netscape format", count)
    return "\n".join(lines) + "\n"


def resolve_cookiefile(raw_path: str | None = None) -> str | None:
    """Return a Netscape cookie file path yt-dlp can read, or None."""
    raw = (raw_path if raw_path is not None else os.getenv("YTDLP_COOKIES_FILE", "")).strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        logger.warning("YTDLP_COOKIES_FILE does not exist: %s", path)
        return None

    head = path.read_bytes()[:8].lstrip()
    if head.startswith(b"[") or head.startswith(b"{"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Cookie JSON is invalid: %s", path)
            return None
        if isinstance(data, dict):
            data = data.get("cookies") or data.get("Cookies") or []
        if not isinstance(data, list):
            logger.warning("Cookie JSON is not a list")
            return None
        filters_env = os.getenv("YTDLP_COOKIE_DOMAINS", "")
        filters = tuple(x.strip().lower() for x in filters_env.split(",") if x.strip()) or _DEFAULT_DOMAIN_FILTERS
        netscape = json_cookies_to_netscape(data, domain_filters=filters)
        dest = Path(tempfile.gettempdir()) / "yt-dlp-cookies.netscape.txt"
        dest.write_text(netscape, encoding="utf-8")
        os.chmod(dest, 0o600)
        return str(dest)

    return str(path)
