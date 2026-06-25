"""Напоминания о тренировках, креатине, воде и сне через APScheduler."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import storage

# Русские дни → коды для cron
DOW = {
    "Понедельник": "mon", "Вторник": "tue", "Среда": "wed", "Четверг": "thu",
    "Пятница": "fri", "Суббота": "sat", "Воскресенье": "sun",
}

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
_bot = None


def _hm(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)


async def _send(uid: int, text: str):
    try:
        await _bot.send_message(uid, text)
    except Exception:
        logging.exception("reminder send failed for %s", uid)


def reschedule_user(uid: int):
    """Пересобирает задания напоминаний пользователя по его настройкам."""
    # снять старые задания пользователя
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{uid}:"):
            job.remove()

    s = storage.get_user(uid)["settings"]

    if s.get("workout_reminder") and s.get("workout_days"):
        dow = ",".join(DOW[d] for d in s["workout_days"] if d in DOW)
        h, m = _hm(s.get("workout_time", "18:00"))
        if dow:
            scheduler.add_job(
                _send, "cron", day_of_week=dow, hour=h, minute=m,
                args=[uid, "🏋️ Пора на тренировку! Не пропускай — ты идёшь к цели 💪"],
                id=f"{uid}:workout", replace_existing=True,
            )

    if s.get("creatine_reminder"):
        h, m = _hm(s.get("creatine_time", "09:00"))
        scheduler.add_job(
            _send, "cron", hour=h, minute=m,
            args=[uid, "💊 Время принять креатин (3–5 г). Запей водой!"],
            id=f"{uid}:creatine", replace_existing=True,
        )

    if s.get("water_reminder"):
        # каждые 2 часа с 10:00 до 20:00
        scheduler.add_job(
            _send, "cron", hour="10,12,14,16,18,20", minute=0,
            args=[uid, "💧 Попей воды и отметь это в боте (вкладка «Вода»)."],
            id=f"{uid}:water", replace_existing=True,
        )

    if s.get("sleep_reminder"):
        h, m = _hm(s.get("sleep_time", "23:00"))
        scheduler.add_job(
            _send, "cron", hour=h, minute=m,
            args=[uid, "😴 Пора готовиться ко сну. Восстановление = рост мышц. Спокойной ночи!"],
            id=f"{uid}:sleep", replace_existing=True,
        )


def start(bot):
    """Запускает планировщик и восстанавливает напоминания всех пользователей."""
    global _bot
    _bot = bot
    if not scheduler.running:
        scheduler.start()
    for uid in storage.all_user_ids():
        reschedule_user(uid)
