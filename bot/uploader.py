from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)


async def upload_file_to_chat(
    bot: Bot,
    *,
    chat_id: int,
    file_path: str,
    title: str = "",
    mime_type: str = "",
    caption: str | None = None,
) -> None:
    """Send a local file via Local Bot API (supports up to 2GB with --local)."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    input_file = FSInputFile(path, filename=path.name)
    text = caption or (title[:900] if title else path.name)

    if mime.startswith("video/") or path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
        await bot.send_video(chat_id=chat_id, video=input_file, caption=text)
    elif mime.startswith("audio/") or path.suffix.lower() in {
        ".mp3",
        ".m4a",
        ".ogg",
        ".flac",
        ".wav",
        ".opus",
        ".aac",
    }:
        await bot.send_audio(chat_id=chat_id, audio=input_file, caption=text)
    elif mime.startswith("image/") and path.suffix.lower() not in {".gif"}:
        await bot.send_photo(chat_id=chat_id, photo=input_file, caption=text)
    else:
        await bot.send_document(chat_id=chat_id, document=input_file, caption=text)

    logger.info("Uploaded %s to chat %s", path.name, chat_id)
