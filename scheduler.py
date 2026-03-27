from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from db import SessionLocal
from tools import run_tool
from app.telegram_api import TelegramAPI


settings = get_settings()
scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.scheduler_timezone))
telegram = TelegramAPI()


async def send_due_reminders() -> None:
    now_local_naive = datetime.now(ZoneInfo(settings.scheduler_timezone)).replace(tzinfo=None)
    async with SessionLocal() as session:
        stmt = (
            select(Reminder)
            .where(Reminder.sent.is_(False), Reminder.due_at <= now_local_naive)
            .order_by(Reminder.due_at.asc())
            .limit(20)
        )
        reminders = (await session.execute(stmt)).scalars().all()
        for item in reminders:
            await telegram.send_message(item.chat_id, f'⏰ Напоминание: {item.text}')
            item.sent = True
        await session.commit()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(send_due_reminders, 'interval', seconds=30, id='send_due_reminders', replace_existing=True)
    scheduler.start()
