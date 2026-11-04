import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import BotCommand

from app import booking as bk
from app import db
from app.config import get_settings
from app.notify import booking_summary

from . import keyboards as kb
from .handlers import router

log = logging.getLogger("bot")

REMINDER_TEXT = {
    "24h": "⏰ Напоминаем: завтра у вас запись.",
    "2h": "⏰ Ждём вас через 2 часа!",
}


async def send_reminders(bot: Bot) -> int:
    sent = 0
    async with db.SessionLocal() as session:
        for b, kind in await bk.due_reminders(session):
            text = f"{REMINDER_TEXT[kind]}\n\n{booking_summary(b)}\n📍 {get_settings().shop_address}"
            try:
                await bot.send_message(b.client.tg_user_id, text, reply_markup=kb.booking_actions(b))
                sent += 1
            except TelegramForbiddenError:
                log.info("Клиент %s заблокировал бота", b.client_id)
            except TelegramAPIError as e:
                log.warning("Напоминание по записи %s не отправлено: %s", b.id, e)
                continue
            await bk.mark_reminded(session, b, kind)
    return sent


async def reminder_loop(bot: Bot) -> None:
    interval = get_settings().reminder_check_sec
    while True:
        try:
            if n := await send_reminders(bot):
                log.info("Отправлено напоминаний: %s", n)
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(interval)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = get_settings().bot_token
    if not token:
        # Без токена контейнер не падает, чтобы остальные сервисы работали.
        log.warning("BOT_TOKEN не задан — бот не запущен. Укажите токен в .env и перезапустите: docker compose up -d bot")
        await asyncio.Event().wait()

    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands(
        [
            BotCommand(command="book", description="Записаться"),
            BotCommand(command="my", description="Мои записи"),
            BotCommand(command="delete_me", description="Удалить мои данные"),
            BotCommand(command="cancel", description="Отменить действие"),
        ]
    )
    reminders = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()


if __name__ == "__main__":
    asyncio.run(main())
