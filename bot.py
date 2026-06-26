"""Телеграм-бот «Зал»: ИИ-тренер, план тренировок, чек-ин, напоминания, трекеры."""
import asyncio
import logging
import os
from datetime import date, datetime

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
    CallbackQuery,
    ErrorEvent,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import ai
import storage
import reminders

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp = Dispatcher()

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

FORM_STEPS = ["sex", "age", "height", "weight", "level", "days", "place", "goal"]
FORM_LABELS = {
    "sex": "пол", "age": "возраст", "height": "рост (см)", "weight": "вес (кг)",
    "level": "уровень", "days": "тренировок в неделю", "place": "место", "goal": "цель",
}
FORM_DISPLAY = {
    "sex": "Пол", "age": "Возраст", "height": "Рост",
    "weight": "Вес", "level": "Уровень", "days": "Тренировок/нед.",
    "place": "Место", "goal": "Цель",
}
FORM_ICONS = {
    "sex": "👤", "age": "🎂", "height": "📏", "weight": "⚖️",
    "level": "📊", "days": "📅", "place": "🏠", "goal": "🎯",
}
FIELD_KEYBOARDS = {
    "sex": ["Мужской", "Женский"],
    "level": ["Новичок", "Средний", "Продвинутый"],
    "days": ["2", "3", "4", "5"],
    "place": ["Зал", "Дома"],
    "goal": ["Похудеть", "Набрать массу", "Рельеф/сушка", "Поддерживать форму"],
}
PLAN_RELEVANT_FIELDS = {"weight", "goal", "level", "days", "sex"}


# ---------- Состояния ----------
class Form(StatesGroup):
    sex = State(); age = State(); height = State(); weight = State()
    level = State(); days = State(); place = State(); goal = State()
    chat = State()


class Plan(StatesGroup):
    name = State(); sets = State(); weight = State()
    edit_value = State()


class Misc(StatesGroup):
    gym_note = State()
    set_time = State()
    set_goal = State()
    custom_intake = State()
    edit_profile = State()


# ---------- Клавиатуры ----------
def kb(*rows) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


MAIN_KB = kb(
    ["📋 Анкета", "🍽 План ИИ"],
    ["🏋️ Мои тренировки", "✅ Пришёл в зал"],
    ["📊 Статистика", "💧 Вода/Белок"],
    ["⏰ Напоминания", "😴 Сон"],
    ["💬 Тренер", "📸 Оценить форму"],
)


def inline(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows
    ])


def split(text: str, limit: int = 4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)] or [""]


async def send_long(target, text: str):
    for chunk in split(text):
        await target.answer(chunk, parse_mode=None)


async def with_thinking(msg: Message, fn, *args):
    note = await msg.answer("⏳ Секундочку, думаю над ответом…")
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    try:
        return await asyncio.to_thread(fn, *args)
    finally:
        try:
            await note.delete()
        except Exception:
            pass


def today() -> str:
    return date.today().isoformat()


def safe_md(s) -> str:
    return (str(s).replace("*", "").replace("_", "")
            .replace("`", "").replace("[", "(").replace("]", ")"))


# ---------- Профиль ----------
def show_profile(profile: dict) -> str:
    """Красиво показывает заполненную анкету."""
    rows = []
    for key in FORM_STEPS:
        val = profile.get(key, "—")
        unit = ""
        if key == "height":
            unit = " см"
        elif key == "weight":
            unit = " кг"
        rows.append(f"{FORM_ICONS[key]} {FORM_DISPLAY[key]}: {val}{unit}")
    return "📋 *Твоя анкета:*\n\n" + "\n".join(rows)


def profile_menu() -> InlineKeyboardMarkup:
    return inline([
        [("✏️ Изменить поле", "profile:edit")],
        [("🔄 Заполнить заново", "profile:refill")],
    ])


def profile_fields_kb() -> InlineKeyboardMarkup:
    return inline([
        [("👤 Пол", "profile:field:sex"), ("🎂 Возраст", "profile:field:age")],
        [("📏 Рост", "profile:field:height"), ("⚖️ Вес", "profile:field:weight")],
        [("📊 Уровень", "profile:field:level"), ("📅 Дни/нед.", "profile:field:days")],
        [("🏠 Место", "profile:field:place"), ("🎯 Цель", "profile:field:goal")],
        [("⬅️ Назад к анкете", "profile:back")],
    ])


# ---------- Старт ----------
@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.clear()
    u = storage.get_user(msg.from_user.id)
    extra = ""
    if u.get("profile") and u["profile"].get("sex"):
        extra = "\n\n✅ Анкета уже заполнена — жми «📋 Анкета» чтобы изменить."
    await msg.answer(
        "🔥 *MASSAGYM* — твой персональный ИИ-тренер в кармане!\n\n"
        "Погнали лепить тело мечты 💪 Вот что я умею:\n\n"
        "🍽 *Питание и тренировки* — подберу диету и программу под твою цель\n"
        "🏋️ *Свой план* — храню и редактирую: вес, подходы, упражнения\n"
        "✅ *Чек-ин в зал* — отмечайся и смотри статистику прогресса\n"
        "⏰ *Напоминания* — тренировки, креатин, вода, сон — ничего не забудешь\n"
        "💧 *Трекеры* — вода и белок под контролем\n"
        "📸 *Оценка формы* — пришли фото, разберу телосложение\n"
        "💬 *Тренер 24/7* — отвечу на любой вопрос и помню наш диалог\n\n"
        "👇 Жми «📋 Анкета» — и начинаем работу над собой!" + extra,
        reply_markup=MAIN_KB,
    )


# ---------- Назад в меню ----------
@dp.message(F.text == "⬅️ Назад")
async def go_back(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Главное меню 👇", reply_markup=MAIN_KB)


# ---------- Анкета: вход ----------
@dp.message(F.text == "📋 Анкета")
@dp.message(Command("form"))
@dp.message(Command("profile"))
async def form_start(msg: Message, state: FSMContext):
    u = storage.get_user(msg.from_user.id)
    if u.get("profile") and u["profile"].get("sex"):
        await msg.answer(
            show_profile(u["profile"]),
            reply_markup=profile_menu(),
        )
    else:
        await state.set_state(Form.sex)
        await msg.answer(
            "Заполним анкету! Это 8 шагов, ~2 минуты.\n\n"
            "*Шаг 1 из 8* — Твой пол?",
            reply_markup=kb(["Мужской", "Женский", "⬅️ Назад"]),
        )


# ---------- Анкета: заполнение ----------
@dp.message(Form.sex)
async def f_sex(msg: Message, state: FSMContext):
    if msg.text not in ("Мужской", "Женский"):
        return await msg.answer("Выбери из списка: Мужской или Женский")
    await state.update_data(sex=msg.text)
    await state.set_state(Form.age)
    await msg.answer("*Шаг 2 из 8* — Сколько тебе лет?", reply_markup=kb(["⬅️ Назад"]))


@dp.message(Form.age)
async def f_age(msg: Message, state: FSMContext):
    if not msg.text.isdigit() or not (10 <= int(msg.text) <= 100):
        return await msg.answer("Введи возраст числом от 10 до 100, например 25")
    await state.update_data(age=msg.text)
    await state.set_state(Form.height)
    await msg.answer("*Шаг 3 из 8* — Твой рост в см?", reply_markup=kb(["⬅️ Назад"]))


@dp.message(Form.height)
async def f_height(msg: Message, state: FSMContext):
    if not msg.text.isdigit() or not (100 <= int(msg.text) <= 250):
        return await msg.answer("Введи рост от 100 до 250 см, например 180")
    await state.update_data(height=msg.text)
    await state.set_state(Form.weight)
    await msg.answer("*Шаг 4 из 8* — Твой вес в кг?", reply_markup=kb(["⬅️ Назад"]))


@dp.message(Form.weight)
async def f_weight(msg: Message, state: FSMContext):
    v = msg.text.replace(".", "", 1)
    if not v.isdigit() or not (30 <= float(msg.text) <= 300):
        return await msg.answer("Введи вес числом от 30 до 300 кг, например 75.5")
    await state.update_data(weight=msg.text)
    await state.set_state(Form.level)
    await msg.answer(
        "*Шаг 5 из 8* — Твой уровень?",
        reply_markup=kb(["Новичок", "Средний", "Продвинутый", "⬅️ Назад"]),
    )


@dp.message(Form.level)
async def f_level(msg: Message, state: FSMContext):
    if msg.text not in ("Новичок", "Средний", "Продвинутый"):
        return await msg.answer("Выбери: Новичок, Средний или Продвинутый")
    await state.update_data(level=msg.text)
    await state.set_state(Form.days)
    await msg.answer(
        "*Шаг 6 из 8* — Сколько тренировок в неделю?",
        reply_markup=kb(["2", "3", "4", "5", "⬅️ Назад"]),
    )


@dp.message(Form.days)
async def f_days(msg: Message, state: FSMContext):
    if msg.text not in ("2", "3", "4", "5"):
        return await msg.answer("Выбери 2, 3, 4 или 5")
    await state.update_data(days=msg.text)
    await state.set_state(Form.place)
    await msg.answer(
        "*Шаг 7 из 8* — Где тренируешься?",
        reply_markup=kb(["Зал", "Дома", "⬅️ Назад"]),
    )


@dp.message(Form.place)
async def f_place(msg: Message, state: FSMContext):
    if msg.text not in ("Зал", "Дома"):
        return await msg.answer("Выбери: Зал или Дома")
    await state.update_data(place=msg.text)
    await state.set_state(Form.goal)
    await msg.answer(
        "*Шаг 8 из 8* — Какой результат хочешь?",
        reply_markup=kb(
            ["Похудеть", "Набрать массу"],
            ["Рельеф/сушка", "Поддерживать форму"],
            ["⬅️ Назад"],
        ),
    )


@dp.message(Form.goal)
async def f_goal(msg: Message, state: FSMContext):
    valid = ("Похудеть", "Набрать массу", "Рельеф/сушка", "Поддерживать форму")
    if msg.text not in valid:
        return await msg.answer("Выбери из списка")
    profile = await state.get_data()
    profile["goal"] = msg.text
    u = storage.get_user(msg.from_user.id)
    u["profile"] = profile
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    await msg.answer("✅ Анкета сохранена! Генерирую план…", reply_markup=MAIN_KB)
    await gen_ai_plan(msg, msg.from_user.id, profile)


# ---------- Редактирование профиля ----------
@dp.callback_query(F.data == "profile:edit")
async def profile_edit(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("Какое поле хочешь изменить?", reply_markup=profile_fields_kb())


@dp.callback_query(F.data == "profile:back")
async def profile_back(cb: CallbackQuery):
    u = storage.get_user(cb.from_user.id)
    await cb.answer()
    await cb.message.edit_text(show_profile(u["profile"]), reply_markup=profile_menu())


@dp.callback_query(F.data == "profile:refill")
async def profile_refill(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "⚠️ Точно заполнить заново? Текущие данные анкеты будут стёрты.\n"
        "План и статистика сохранятся.",
        reply_markup=inline([
            [("✅ Да, заполнить заново", "profile:confirm_refill")],
            [("⬅️ Отмена", "profile:back")],
        ]),
    )


@dp.callback_query(F.data == "profile:confirm_refill")
async def profile_confirm_refill(cb: CallbackQuery, state: FSMContext):
    u = storage.get_user(cb.from_user.id)
    u["profile"] = {}
    storage.save_user(cb.from_user.id, u)
    await state.set_state(Form.sex)
    await cb.answer()
    await cb.message.answer(
        "Окей, заполняем заново!\n\n*Шаг 1 из 8* — Твой пол?",
        reply_markup=kb(["Мужской", "Женский", "⬅️ Назад"]),
    )


@dp.callback_query(F.data.startswith("profile:field:"))
async def profile_edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[2]
    if field not in FORM_DISPLAY:
        return await cb.answer("Неизвестное поле")
    u = storage.get_user(cb.from_user.id)
    current = u["profile"].get(field, "—")
    label = FORM_DISPLAY[field]

    await state.update_data(edit_field=field)
    await state.set_state(Misc.edit_profile)
    await cb.answer()

    text = f"*{label}*\nТекущее значение: *{current}*\n\nВведи новое:"
    if field in FIELD_KEYBOARDS:
        opts = FIELD_KEYBOARDS[field]
        if len(opts) <= 2:
            rows = [opts]
        elif len(opts) <= 4:
            rows = [opts[:2], opts[2:]]
        else:
            rows = [opts[:2], opts[2:]]
        rows.append(["⬅️ Назад"])
        await cb.message.answer(text, reply_markup=kb(*rows))
    else:
        await cb.message.answer(text, reply_markup=kb(["⬅️ Назад"]))


@dp.message(Misc.edit_profile)
async def edit_profile_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")
    if not field:
        await state.clear()
        return

    val = msg.text.strip()

    # Валидация по полям
    if field == "sex" and val not in ("Мужской", "Женский"):
        return await msg.answer("Выбери: Мужской или Женский")
    elif field == "age":
        if not val.isdigit() or not (10 <= int(val) <= 100):
            return await msg.answer("Введи возраст от 10 до 100")
    elif field == "height":
        if not val.isdigit() or not (100 <= int(val) <= 250):
            return await msg.answer("Введи рост от 100 до 250 см")
    elif field == "weight":