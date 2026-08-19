from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from bot.api_client import ApiError, DjangoApiClient
from bot.config import get_settings
from bot.timecode import TimecodeError, format_timecode, parse_timecode
from bot.uploader import upload_file_to_chat

logger = logging.getLogger(__name__)
router = Router()

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# (user_id, quality_message_id) -> {url, formats, duration}
_pending: dict[tuple[int, int], dict] = {}

# (user_id, mode_message_id) -> {url, format, label, duration}
_clip_pending: dict[tuple[int, int], dict] = {}


class ClipStates(StatesGroup):
    waiting_start = State()
    waiting_end = State()


def _is_allowed(user_id: int) -> bool:
    allowed = get_settings().allowed_ids
    if not allowed:
        return True
    return user_id in allowed


def _required_channel() -> str:
    return (get_settings().required_channel or "").strip()


def _join_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    url = settings.required_channel_url or f"https://t.me/{_required_channel().lstrip('@')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="𓆩  عضویت در کانال  𓆪", url=url)],
            [InlineKeyboardButton(text="✅ تایید عضویت", callback_data="join:check")],
        ]
    )


async def _is_channel_member(bot: Bot, user_id: int) -> bool:
    chat = _required_channel()
    if not chat:
        return True
    try:
        member = await bot.get_chat_member(chat, user_id)
    except TelegramBadRequest as exc:
        logger.warning("channel membership check failed: %s", exc)
        return False
    except Exception:  # noqa: BLE001
        logger.exception("channel membership check failed")
        return False
    return member.status in {"creator", "administrator", "member", "restricted"}


async def _require_join(target: Message | CallbackQuery) -> bool:
    user = target.from_user
    bot = target.bot
    if not user or bot is None:
        return False
    if await _is_channel_member(bot, user.id):
        return True
    text = (
        "برای استفاده از ربات باید عضو کانال باشید.\n\n"
        "۱. دکمه شیشه‌ای «عضویت در کانال» را بزنید\n"
        "۲. بعد از عضویت، «تایید عضویت» را بزنید"
    )
    markup = _join_keyboard()
    if isinstance(target, CallbackQuery):
        await target.answer("اول در کانال عضو شوید", show_alert=True)
        if target.message:
            try:
                await target.message.answer(text, reply_markup=markup)
            except Exception:  # noqa: BLE001
                pass
    else:
        await target.answer(text, reply_markup=markup)
    return False


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


def _quality_keyboard(formats: list[dict], message_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, fmt in enumerate(formats):
        row.append(
            InlineKeyboardButton(
                text=str(fmt.get("label") or fmt.get("id") or "کیفیت"),
                callback_data=f"q:{message_id}:{idx}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mode_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 ویدیوی کامل", callback_data=f"mode:full:{message_id}")],
            [InlineKeyboardButton(text="✂️ فقط بخشی از ویدیو", callback_data=f"mode:part:{message_id}")],
        ]
    )


def _clip_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data="clip:cancel")]]
    )


def _cancel_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏹ لغو دانلود", callback_data=f"cancel:{job_id}")]
        ]
    )


def _default_formats() -> list[dict]:
    return [
        {"id": "best", "label": "بهترین کیفیت"},
        {"id": "audio", "label": "فقط صدا (MP3)"},
    ]


def _duration_hint(duration_seconds: int) -> str:
    if duration_seconds <= 0:
        return ""
    return f"\n\nطول کل ویدیو: {format_timecode(duration_seconds * 1000)}"


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user or not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return
    if not await _require_join(message):
        return
    await message.answer(
        "سلام! 👋\n\n"
        "لینک ویدیو یا فایل را بفرستید تا دانلود کنم.\n"
        "چند لینک را پشت‌سرهم بفرستید تا همزمان دانلود شوند.\n"
        "کیفیت را از دکمه‌ها انتخاب کنید، سپس مشخص کنید ویدیوی کامل یا فقط بخشی از آن را می‌خواهید.\n\n"
        "سقف حجم: ۲ گیگابایت\n"
        "/help برای راهنما"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not message.from_user or not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return
    if not await _require_join(message):
        return
    await message.answer(
        "📖 راهنما\n\n"
        "• لینک بفرستید → کیفیت را انتخاب کنید\n"
        "• بعد از انتخاب کیفیت مشخص کنید ویدیوی کامل یا فقط بخشی از آن را می‌خواهید\n"
        "• برای برش، زمان شروع و پایان را به‌صورت «دقیقه:ثانیه:میلی‌ثانیه» بفرستید (مثلاً 1:23:500 یا 1:23 یا 1)\n"
        "• چند لینک = چند دانلود همزمان\n"
        "• دکمه «لغو دانلود» جاب را متوقف می‌کند\n\n"
        "/start — شروع\n"
        "/help — همین پیام"
    )


@router.message(F.text, StateFilter(None))
async def on_text(message: Message, api: DjangoApiClient) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return
    if not await _require_join(message):
        return

    match = URL_RE.search(message.text)
    if not match:
        await message.answer("لطفاً یک لینک معتبر (http/https) بفرستید.")
        return

    url = match.group(0).rstrip(").,]}>\"'")
    user = message.from_user

    if _looks_like_direct(url):
        asyncio.create_task(
            _run_job(message, api, url=url, preferred_format="best", user=user)
        )
        return

    wait = await message.answer("🔎 در حال خواندن کیفیت‌های موجود…")
    formats = _default_formats()
    title = ""
    duration = 0
    try:
        probed = await api.probe(url, telegram_user_id=user.id)
        formats = probed.get("formats") or formats
        title = probed.get("title") or ""
        duration = int(probed.get("duration") or 0)
    except ApiError as exc:
        logger.warning("probe failed: %s", exc)
        await wait.edit_text(
            f"نتوانستم لیست کیفیت را کامل بخوانم ({exc}).\nکیفیت کلی را انتخاب کنید:"
        )
    else:
        head = f"{title}\n\n" if title else ""
        await wait.edit_text(f"{head}کیفیت را انتخاب کنید:")

    _pending[(user.id, wait.message_id)] = {"url": url, "formats": formats, "duration": duration}
    try:
        await wait.edit_reply_markup(reply_markup=_quality_keyboard(formats, wait.message_id))
    except Exception:  # noqa: BLE001
        logger.exception("failed to attach quality keyboard")


@router.callback_query(F.data == "join:check")
async def on_join_check(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    if not _is_allowed(callback.from_user.id):
        await callback.answer("دسترسی مجاز نیست", show_alert=True)
        return
    bot = callback.bot
    if bot is None:
        await callback.answer("ربات در دسترس نیست", show_alert=True)
        return
    if await _is_channel_member(bot, callback.from_user.id):
        await callback.answer("عضویت تایید شد ✅", show_alert=True)
        if callback.message:
            try:
                await callback.message.edit_text(
                    "عضویت شما تایید شد.\nحالا لینک ویدیو یا فایل را بفرستید."
                )
            except Exception:  # noqa: BLE001
                pass
        return
    await callback.answer("هنوز عضو کانال نیستید", show_alert=True)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=_join_keyboard())
        except Exception:  # noqa: BLE001
            pass


@router.callback_query(F.data.startswith("q:"))
async def on_quality(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        return
    if not _is_allowed(callback.from_user.id):
        await callback.answer("دسترسی مجاز نیست", show_alert=True)
        return
    if not await _require_join(callback):
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("نامعتبر")
        return
    try:
        msg_id = int(parts[1])
        idx = int(parts[2])
    except ValueError:
        await callback.answer("نامعتبر")
        return

    pending = _pending.pop((callback.from_user.id, msg_id), None)
    if not pending:
        await callback.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرستید.", show_alert=True)
        return

    formats = pending.get("formats") or _default_formats()
    if idx < 0 or idx >= len(formats):
        await callback.answer("کیفیت نامعتبر")
        return
    fmt_id = str(formats[idx].get("id") or "best")
    label = str(formats[idx].get("label") or fmt_id)
    duration = int(pending.get("duration") or 0)

    await callback.answer(label)

    _clip_pending[(callback.from_user.id, callback.message.message_id)] = {
        "url": pending["url"],
        "format": fmt_id,
        "label": label,
        "duration": duration,
    }
    try:
        await callback.message.edit_text(
            f"کیفیت انتخاب‌شده: {label}\n\nویدیوی کامل ارسال شود یا فقط بخشی از آن؟",
            reply_markup=_mode_keyboard(callback.message.message_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to show full/part keyboard")


@router.callback_query(F.data.startswith("mode:"))
async def on_mode(callback: CallbackQuery, api: DjangoApiClient, state: FSMContext) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        return
    if not _is_allowed(callback.from_user.id):
        await callback.answer("دسترسی مجاز نیست", show_alert=True)
        return
    if not await _require_join(callback):
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("نامعتبر")
        return
    mode = parts[1]
    try:
        msg_id = int(parts[2])
    except ValueError:
        await callback.answer("نامعتبر")
        return

    pending = _clip_pending.pop((callback.from_user.id, msg_id), None)
    if not pending:
        await callback.answer("این انتخاب منقضی شده؛ لینک را دوباره بفرستید.", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    if mode == "full":
        asyncio.create_task(
            _run_job(
                callback.message,
                api,
                url=pending["url"],
                preferred_format=pending["format"],
                user=callback.from_user,
                quality_label=pending["label"],
            )
        )
        return

    await state.set_state(ClipStates.waiting_start)
    await state.update_data(**pending)
    hint = _duration_hint(pending.get("duration") or 0)
    await callback.message.answer(
        "⏱ زمان شروع برش را بفرستید.\n\n"
        "فرمت: دقیقه:ثانیه:میلی‌ثانیه — مثلاً «1:23:500» یا «1:23» یا «1»\n"
        "(اگر میلی‌ثانیه ننویسید صفر و اگر ثانیه هم ننویسید صفر در نظر گرفته می‌شود)"
        f"{hint}",
        reply_markup=_clip_cancel_keyboard(),
    )


@router.callback_query(F.data == "clip:cancel")
async def on_clip_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("لغو شد")
    if callback.message:
        try:
            await callback.message.edit_text("لغو شد. لینک را دوباره بفرستید.")
        except Exception:  # noqa: BLE001
            pass


@router.message(ClipStates.waiting_start, F.text)
async def on_clip_start_time(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return

    try:
        start_ms = parse_timecode(message.text)
    except TimecodeError as exc:
        await message.answer(
            f"❌ {exc}\nدوباره بفرستید؛ مثلاً «1:23» یا «1:23:500»:",
            reply_markup=_clip_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    duration = int(data.get("duration") or 0)
    if duration and start_ms >= duration * 1000:
        await message.answer(
            f"❌ زمان شروع از طول ویدیو ({format_timecode(duration * 1000)}) بیشتر است. دوباره بفرستید:",
            reply_markup=_clip_cancel_keyboard(),
        )
        return

    await state.update_data(clip_start_ms=start_ms)
    await state.set_state(ClipStates.waiting_end)
    await message.answer(
        f"✅ شروع برش: {format_timecode(start_ms)}\n\n⏱ حالا زمان پایان برش را بفرستید:",
        reply_markup=_clip_cancel_keyboard(),
    )


@router.message(ClipStates.waiting_end, F.text)
async def on_clip_end_time(message: Message, api: DjangoApiClient, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_allowed(message.from_user.id):
        await message.answer("⛔ دسترسی شما مجاز نیست.")
        return

    try:
        end_ms = parse_timecode(message.text)
    except TimecodeError as exc:
        await message.answer(f"❌ {exc}\nدوباره بفرستید:", reply_markup=_clip_cancel_keyboard())
        return

    data = await state.get_data()
    start_ms = int(data.get("clip_start_ms") or 0)
    duration = int(data.get("duration") or 0)

    if end_ms <= start_ms:
        await message.answer(
            "❌ زمان پایان باید بعد از زمان شروع باشد. دوباره بفرستید:",
            reply_markup=_clip_cancel_keyboard(),
        )
        return
    if duration and end_ms > duration * 1000:
        await message.answer(
            f"❌ زمان پایان از طول ویدیو ({format_timecode(duration * 1000)}) بیشتر است. دوباره بفرستید:",
            reply_markup=_clip_cancel_keyboard(),
        )
        return

    url = data.get("url")
    fmt = data.get("format")
    label = data.get("label") or ""
    await state.clear()

    if not url or not fmt or not message.from_user:
        await message.answer("❌ اطلاعات دانلود منقضی شده؛ لینک را دوباره بفرستید.")
        return

    clip_note = f"برش {format_timecode(start_ms)}–{format_timecode(end_ms)}"
    extra_label = f"{label} | {clip_note}" if label else clip_note

    asyncio.create_task(
        _run_job(
            message,
            api,
            url=url,
            preferred_format=fmt,
            user=message.from_user,
            quality_label=extra_label,
            clip_start_ms=start_ms,
            clip_end_ms=end_ms,
        )
    )


@router.callback_query(F.data.startswith("cancel:"))
async def on_cancel(callback: CallbackQuery, api: DjangoApiClient) -> None:
    if not callback.from_user or not callback.data:
        return
    if not _is_allowed(callback.from_user.id):
        await callback.answer("دسترسی مجاز نیست", show_alert=True)
        return
    if not await _require_join(callback):
        return
    try:
        job_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("نامعتبر")
        return
    try:
        await api.cancel_job(job_id)
    except ApiError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("لغو شد")
    if callback.message:
        try:
            await callback.message.edit_text(f"⏹ دانلود #{job_id} لغو شد.")
        except Exception:  # noqa: BLE001
            pass


async def _run_job(
    message: Message,
    api: DjangoApiClient,
    *,
    url: str,
    preferred_format: str,
    user: User,
    quality_label: str = "",
    clip_start_ms: int | None = None,
    clip_end_ms: int | None = None,
) -> None:
    extra = f" ({quality_label})" if quality_label else ""
    status_msg = await message.answer(f"⏳ در حال ایجاد جاب دانلود{extra}…")

    try:
        job = await api.create_job(
            url=url,
            telegram_user_id=user.id,
            chat_id=message.chat.id,
            preferred_format=preferred_format,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            language_code=user.language_code or "",
            clip_start_ms=clip_start_ms,
            clip_end_ms=clip_end_ms,
        )
    except ApiError as exc:
        await status_msg.edit_text(f"❌ خطا: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_job failed")
        await status_msg.edit_text(f"❌ خطا در ارتباط با API: {exc}")
        return

    job_id = job["id"]
    await status_msg.edit_text(
        f"📥 دانلود شروع شد (#{job_id}){extra}…",
        reply_markup=_cancel_keyboard(job_id),
    )

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

        if status == "canceled":
            await status_msg.edit_text(f"⏹ دانلود #{job_id} لغو شد.")
            return
        if status == "downloading" and progress != last_progress:
            last_progress = progress
            await status_msg.edit_text(
                f"📥 در حال دانلود… {progress}% (#{job_id}){extra}",
                reply_markup=_cancel_keyboard(job_id),
            )
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
                    thumbnail_path=job.get("thumbnail_path") or "",
                    width=int(job.get("width") or 0),
                    height=int(job.get("height") or 0),
                    duration=int(job.get("duration") or 0),
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
