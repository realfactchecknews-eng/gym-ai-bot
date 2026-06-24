"""Телеграм-бот «Зал»: анкета → ИИ подбирает диету и тренировки + анализ формы по фото."""
import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

import ai
import storage

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp = Dispatcher()


# ---------- Состояния анкеты ----------
class Form(StatesGroup):
    sex = State()
    age = State()
    height = State()
    weight = State()
    level = State()
    days = State()
    place = State()
    goal = State()
    chat = State()  # свободный чат с тренером


def kb(*rows) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


MAIN_KB = kb(
    ["📋 Заполнить анкету"],
    ["💪 Мой план", "📸 Оценить форму"],
    ["💬 Спросить тренера"],
)


# ---------- Старт ----------
@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Привет! Я твой ИИ-тренер.\n\n"
        "Заполни короткую анкету — и я подберу *персональную диету* и "
        "*программу тренировок*. А ещё могу оценить твою форму по фото "
        "и подсказать, что подкачать.\n\n"
        "Жми «📋 Заполнить анкету».",
        reply_markup=MAIN_KB,
    )


# ---------- Анкета ----------
@dp.message(F.text == "📋 Заполнить анкету")
@dp.message(Command("form"))
async def form_start(msg: Message, state: FSMContext):
    await state.set_state(Form.sex)
    await msg.answer("Твой пол?", reply_markup=kb(["Мужской", "Женский"]))


@dp.message(Form.sex)
async def f_sex(msg: Message, state: FSMContext):
    await state.update_data(sex=msg.text)
    await state.set_state(Form.age)
    await msg.answer("Сколько тебе лет?", reply_markup=ReplyKeyboardRemove())


@dp.message(Form.age)
async def f_age(msg: Message, state: FSMContext):
    if not msg.text.isdigit():
        return await msg.answer("Введи возраст числом, например 25")
    await state.update_data(age=msg.text)
    await state.set_state(Form.height)
    await msg.answer("Твой рост в см?")


@dp.message(Form.height)
async def f_height(msg: Message, state: FSMContext):
    if not msg.text.isdigit():
        return await msg.answer("Введи рост числом в см, например 180")
    await state.update_data(height=msg.text)
    await state.set_state(Form.weight)
    await msg.answer("Твой вес в кг?")


@dp.message(Form.weight)
async def f_weight(msg: Message, state: FSMContext):
    if not msg.text.replace(".", "", 1).isdigit():
        return await msg.answer("Введи вес числом в кг, например 75")
    await state.update_data(weight=msg.text)
    await state.set_state(Form.level)
    await msg.answer(
        "Твой уровень подготовки?",
        reply_markup=kb(["Новичок", "Средний", "Продвинутый"]),
    )


@dp.message(Form.level)
async def f_level(msg: Message, state: FSMContext):
    await state.update_data(level=msg.text)
    await state.set_state(Form.days)
    await msg.answer(
        "Сколько раз в неделю готов тренироваться?",
        reply_markup=kb(["2", "3", "4", "5"]),
    )


@dp.message(Form.days)
async def f_days(msg: Message, state: FSMContext):
    await state.update_data(days=msg.text)
    await state.set_state(Form.place)
    await msg.answer("Где тренируешься?", reply_markup=kb(["Зал", "Дома"]))


@dp.message(Form.place)
async def f_place(msg: Message, state: FSMContext):
    await state.update_data(place=msg.text)
    await state.set_state(Form.goal)
    await msg.answer(
        "Какой результат хочешь?",
        reply_markup=kb(
            ["Похудеть", "Набрать массу"],
            ["Рельеф/сушка", "Поддерживать форму"],
        ),
    )


@dp.message(Form.goal)
async def f_goal(msg: Message, state: FSMContext):
    await state.update_data(goal=msg.text)
    data = await state.get_data()
    storage.save_profile(msg.from_user.id, data)
    await state.clear()
    await msg.answer("✅ Анкета сохранена! Генерирую план...", reply_markup=MAIN_KB)
    await generate_plan(msg, data)


async def generate_plan(msg: Message, profile: dict):
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    try:
        plan = await asyncio.to_thread(ai.build_plan, profile)
    except Exception as e:
        logging.exception("plan error")
        return await msg.answer(f"⚠️ Не удалось сгенерировать план: {e}")
    for chunk in split(plan):
        await msg.answer(chunk)


# ---------- Мой план ----------
@dp.message(F.text == "💪 Мой план")
async def my_plan(msg: Message):
    profile = storage.get_profile(msg.from_user.id)
    if not profile:
        return await msg.answer("Сначала заполни анкету 📋")
    await msg.answer("🔄 Обновляю твой план...")
    await generate_plan(msg, profile)


# ---------- Оценка формы по фото ----------
@dp.message(F.text == "📸 Оценить форму")
async def ask_photo(msg: Message):
    await msg.answer(
        "Пришли фото в полный рост (можно в спортивной форме) — "
        "оценю телосложение и подскажу, что качать 💪"
    )


@dp.message(F.photo)
async def on_photo(msg: Message):
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    file = await bot.get_file(msg.photo[-1].file_id)
    buf = await bot.download_file(file.file_path)
    image_bytes = buf.read()
    profile = storage.get_profile(msg.from_user.id)
    try:
        result = await asyncio.to_thread(ai.analyze_photo, image_bytes, profile)
    except Exception as e:
        logging.exception("vision error")
        return await msg.answer(f"⚠️ Не удалось проанализировать фото: {e}")
    for chunk in split(result):
        await msg.answer(chunk)


# ---------- Свободный чат с тренером ----------
@dp.message(F.text == "💬 Спросить тренера")
async def chat_start(msg: Message, state: FSMContext):
    await state.set_state(Form.chat)
    await msg.answer(
        "Задай любой вопрос про тренировки, питание или восстановление. "
        "Для выхода — /start"
    )


@dp.message(Form.chat)
async def chat_answer(msg: Message, state: FSMContext):
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    profile = storage.get_profile(msg.from_user.id)
    try:
        answer = await asyncio.to_thread(ai.ask_coach, msg.text, profile)
    except Exception as e:
        logging.exception("chat error")
        return await msg.answer(f"⚠️ Ошибка: {e}")
    for chunk in split(answer):
        await msg.answer(chunk)


# ---------- Фолбэк ----------
@dp.message(StateFilter(None))
async def fallback(msg: Message):
    await msg.answer("Выбери действие на клавиатуре ниже 👇", reply_markup=MAIN_KB)


def split(text: str, limit: int = 4000):
    """Режет длинный ответ под лимит Telegram."""
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]


async def main():
    if not os.getenv("BOT_TOKEN") or not os.getenv("OPENROUTER_BASE_URL"):
        raise SystemExit("Заполни BOT_TOKEN и OPENROUTER_BASE_URL в .env")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
