"""Фоновые рассылки: просьба об отзыве, повторная запись, лист ожидания."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app import db
from app import engagement as eg

from . import keyboards as kb

log = logging.getLogger("bot.jobs")


async def _send(bot: Bot, chat_id: int, text: str, markup) -> bool:
    try:
        await bot.send_message(chat_id, text, reply_markup=markup)
        return True
    except TelegramAPIError as e:
        log.info("Сообщение %s не доставлено: %s", chat_id, e)
        return False


async def ask_reviews(bot: Bot) -> int:
    sent = 0
    async with db.SessionLocal() as session:
        for b in await eg.due_review_requests(session):
            text = f"Как прошёл визит к мастеру {b.master.name}? Оцените, пожалуйста — это займёт секунду."
            sent += await _send(bot, b.client.tg_user_id, text, kb.stars(b.id))
            b.review_asked = True  # даже если не доставлено — не повторяем
        await session.commit()
    return sent


async def offer_rebooking(bot: Bot) -> int:
    sent = 0
    async with db.SessionLocal() as session:
        for b in await eg.due_rebook_offers(session):
            weeks = max(1, b.service.rebook_days // 7)
            text = (
                f"{b.client.name or 'Здравствуйте'}, прошло около {weeks} нед. с последнего визита. "
                f"Записать вас снова к мастеру {b.master.name} на «{b.service.name}»?"
            )
            sent += await _send(bot, b.client.tg_user_id, text, kb.rebook(b.id))
            await eg.mark_rebook_offered(session, b)
    return sent


async def notify_waitlist(bot: Bot) -> int:
    sent = 0
    async with db.SessionLocal() as session:
        for entry, master, slots in await eg.due_waitlist(session):
            text = (
                f"🎉 Освободилось время {kb.short_date(entry.day)} у мастера {master.name} "
                f"на «{entry.service.name}». Успейте выбрать — кто первый нажмёт, того и время:"
            )
            sent += await _send(bot, entry.client.tg_user_id, text, kb.waitlist_offer(master.id, entry.service_id, slots))
            await eg.mark_waitlist_notified(session, entry)
    return sent
