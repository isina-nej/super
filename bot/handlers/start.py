from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.api_client import ApiError, DjangoApiClient
from bot.config import get_settings
from bot.uploader import upload_file_to_chat

logger = logging.getLogger(__name__)
router = Router()

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Temporary URL wait for quality selection: telegram_user_id -> url
_pending_urls: dict[int, str] = {}


def _is_allowed(user_id: int) -> bool:
    allowed = get_settings().allowed_ids
    if not allowed:
        return True
    return user_id in allowed


def _looks_like_direct(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return any(
        path.endswith(ext)
        for ext in (
            ".mp4",
            ".mkv",
            ".webm",
            ".mp3",
            ".m4a",
            ".pdf",
            ".zip",
            ".jpg",
            ".png",
            ".gif",
        )
    )


def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="بهترین کیفیت", callback_data="fmt:best"),
                InlineKeyboardButton(text="فقط صدا", callback_data="fmt:audio"),
            ]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user or not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return
    await message.answer(
        "سلام! 👋\n\n"
        "لینک ویدیو یا فایل را بفرستید تا دانلود کنم.\n"
        "پشتیبانی از یوتیوب، اینستاگرام، تیک‌تاک و لینک مستقیم فایل.\n\n"
        "سقف حجم: ۲ گیگابایت (Local Bot API)\n"
        "/help برای راهنما"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 راهنما\n\n"
        "۱. لینک را ارسال کنید\n"
        "۲. برای لینک‌های مدیا، کیفیت را انتخاب کنید\n"
        "۳. صبر کنید تا فایل آماده و ارسال شود\n\n"
        "دستورات:\n"
        "/start — شروع\n"
        "/help — همین پیام"
    )


@router.message(F.text)
async def on_text(message: Message, api: DjangoApiClient) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return

    match = URL_RE.search(message.text)
    if not match:
        await message.answer("لطفاً یک لینک معتبر (http/https) بفرستید.")
        return

    url = match.group(0).rstrip(").,]}>\"'")
    user_id = message.from_user.id

    if _looks_like_direct(url):
        await _start_job(
            message,
            api,
            url=url,
            preferred_format="best",
        )
        return

    _pending_urls[user_id] = url
    await message.answer(
        "لینک دریافت شد. کیفیت را انتخاب کنید:",
        reply_markup=quality_keyboard(),
    )


@router.callback_query(F.data.startswith("fmt:"))
async def on_format(callback: CallbackQuery, api: DjangoApiClient) -> None:
    if not callback.from_user or not callback.message:
        return
    if not _is_allowed(callback.from_user.id):
        await callback.answer("دسترسی مجاز نیست", show_alert=True)
        return

    fmt = callback.data.split(":", 1)[1]
    if fmt not in {"best", "audio"}:
        await callback.answer("نامعتبر")
        return

    url = _pending_urls.pop(callback.from_user.id, None)
    if not url:
        await callback.answer("لینک منقضی شده؛ دوباره بفرستید.", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    await _start_job(
        callback.message,
        api,
        url=url,
        preferred_format=fmt,
        user=callback.from_user,
    )


async def _start_job(
    message: Message,
    api: DjangoApiClient,
    *,
    url: str,
    preferred_format: str,
    user=None,
) -> None:
    from_user = user or message.from_user
    if not from_user:
        return

    status_msg = await message.answer("⏳ در حال ایجاد جاب دانلود…")

    try:
        job = await api.create_job(
            url=url,
            telegram_user_id=from_user.id,
            chat_id=message.chat.id,
            preferred_format=preferred_format,
            username=from_user.username or "",
            first_name=from_user.first_name or "",
            last_name=from_user.last_name or "",
            language_code=from_user.language_code or "",
        )
    except ApiError as exc:
        await status_msg.edit_text(f"❌ خطا: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_job failed")
        await status_msg.edit_text(f"❌ خطا در ارتباط با API: {exc}")
        return

    job_id = job["id"]
    await status_msg.edit_text(f"📥 دانلود شروع شد (#{job_id})…")

    settings = get_settings()
    elapsed = 0.0
    last_progress = -1

    while elapsed < settings.poll_timeout_seconds:
        await asyncio.sleep(settings.poll_interval_seconds)
        elapsed += settings.poll_interval_seconds
        try:
            job = await api.get_job(job_id)
        except ApiError as exc:
            await status_msg.edit_text(f"❌ خطا در دریافت وضعیت: {exc}")
            return

        status = job.get("status")
        progress = int(job.get("progress") or 0)

        if status == "downloading" and progress != last_progress:
            last_progress = progress
            await status_msg.edit_text(f"📥 در حال دانلود… {progress}% (#{job_id})")
        elif status == "ready":
            file_path = job.get("file_path") or ""
            await status_msg.edit_text("📤 در حال ارسال فایل…")
            try:
                await upload_file_to_chat(
                    message.bot,
                    chat_id=message.chat.id,
                    file_path=file_path,
                    title=job.get("title") or "",
                    mime_type=job.get("mime_type") or "",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("upload failed for job %s", job_id)
                await status_msg.edit_text(f"❌ ارسال فایل ناموفق: {exc}")
                return

            try:
                await api.ack_job(job_id)
            except ApiError as exc:
                logger.warning("ack failed for job %s: %s", job_id, exc)

            await status_msg.edit_text("✅ فایل ارسال شد.")
            return
        elif status == "failed":
            err = job.get("error") or "دانلود ناموفق بود."
            await status_msg.edit_text(f"❌ {err}")
            return
        elif status in {"expired", "acked"}:
            await status_msg.edit_text("⚠️ این جاب دیگر معتبر نیست.")
            return

    await status_msg.edit_text("⏱️ زمان انتظار تمام شد. بعداً دوباره تلاش کنید.")
