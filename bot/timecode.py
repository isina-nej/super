"""Parsing/formatting for the "MM:SS:mmm" clip timecodes users type in chat."""

from __future__ import annotations


class TimecodeError(ValueError):
    """Raised when a user-supplied timecode string can't be parsed."""


def parse_timecode(text: str) -> int:
    """Parse "MM:SS:mmm" / "MM:SS" / "MM" into total milliseconds.

    The biggest unit is minutes (not hours) per the bot's UX. Missing
    trailing parts default to zero:
      * "5"        -> 5 minutes, 0 seconds, 0 ms
      * "5:30"     -> 5 minutes, 30 seconds, 0 ms
      * "5:30:250" -> 5 minutes, 30 seconds, 250 ms
    """
    raw = (text or "").strip()
    if not raw:
        raise TimecodeError("زمان نمی‌تواند خالی باشد.")

    parts = raw.split(":")
    if len(parts) > 3:
        raise TimecodeError(
            "فرمت زمان نامعتبر است. حداکثر «دقیقه:ثانیه:میلی‌ثانیه» را بفرستید؛ مثلاً 1:23:500"
        )

    parts = [p.strip() for p in parts]
    while len(parts) < 3:
        parts.append("0")
    minute_s, second_s, ms_s = parts

    if not (minute_s.isdigit() and second_s.isdigit() and ms_s.isdigit()):
        raise TimecodeError("زمان باید فقط شامل عدد باشد؛ مثلاً 1:23:500 یا 1:23 یا 1")

    minute, second, ms = int(minute_s), int(second_s), int(ms_s)
    if second > 59:
        raise TimecodeError("ثانیه باید بین ۰ تا ۵۹ باشد.")
    if ms > 999:
        raise TimecodeError("میلی‌ثانیه باید بین ۰ تا ۹۹۹ باشد.")

    return (minute * 60 + second) * 1000 + ms


def format_timecode(total_ms: int) -> str:
    """Format milliseconds back into MM:SS(.mmm) for user-facing messages."""
    total_ms = max(0, int(total_ms))
    total_seconds, ms = divmod(total_ms, 1000)
    minute, second = divmod(total_seconds, 60)
    if ms:
        return f"{minute:02d}:{second:02d}.{ms:03d}"
    return f"{minute:02d}:{second:02d}"
