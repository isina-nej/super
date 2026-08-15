from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

# Allow `python -m bot.main` from project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.api_client import DjangoApiClient
from bot.config import get_settings
from bot.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="[{levelname}] {asctime} {name}: {message}",
    style="{",
)
logger = logging.getLogger("bot")


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is required")

    api_server = TelegramAPIServer.from_base(settings.local_api_base, is_local=True)
    session = AiohttpSession(api=api_server)
    bot = Bot(token=settings.bot_token, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    api = DjangoApiClient()

    dp["api"] = api
    dp.include_router(router)

    # Inject api into handlers via workflow data
    @dp.update.outer_middleware()
    async def inject_api(handler, event, data):
        data["api"] = api
        return await handler(event, data)

    logger.info("Bot starting (Local Bot API: %s)", settings.local_api_base)
    try:
        await dp.start_polling(bot)
    finally:
        await api.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
