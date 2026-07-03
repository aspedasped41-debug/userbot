from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import router
from config import load_settings
from userbot.manager import UserbotManager


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())

    manager = UserbotManager(settings=settings, bot=bot)
    dispatcher["manager"] = manager
    dispatcher.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Qayta boshlash | Перезапустить"),
            BotCommand(command="status", description="Holatni tekshirish | Проверить статус"),
            BotCommand(command="logout", description="Chiqish | Выход"),
        ]
    )
    await manager.start_existing_sessions()

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await manager.stop_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
