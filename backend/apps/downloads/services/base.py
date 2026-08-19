"""Download service primitives (platform-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


ProgressCallback = Optional[Callable[[int], None]]


@dataclass
class DownloadResult:
    file_path: str
    source_type: str
    title: str = ""
    mime_type: str = ""
    file_size: int = 0
    thumbnail_path: str = ""
    width: int = 0
    height: int = 0
    duration: int = 0


class DownloadError(Exception):
    """Raised when a download cannot complete."""


class CancelledDownload(DownloadError):
    def __init__(self) -> None:
        super().__init__("دانلود لغو شد.")


class FileTooLargeError(DownloadError):
    def __init__(self, size: int, limit: int) -> None:
        self.size = size
        self.limit = limit
        super().__init__(
            f"حجم فایل ({size} بایت) از سقف مجاز ({limit} بایت) بیشتر است."
        )
