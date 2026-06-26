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
        v = val.replace(".", "", 1)
        if not v.isdigit() or not (30 <= float(val) <= 300):
            return await msg.answer("Введи вес от 30 до 300 кг")
    elif field == "level" and val not in ("Новичок", "Средний", "Продвинутый"):
        return await msg.answer("Выбери: Новичок, Средний или Продвинутый")
    elif field == "days" and val not in ("2", "3", "4", "5"):
        return await msg.answer("Выбери 2, 3, 4 или 5")
    elif field == "place" and val not in ("Зал", "Дома"):
        return await msg.answer("Выбери: Зал или Дома")
    elif field == "goal" and val not in ("Похудеть", "Набрать массу", "Рельеф/сушка", "Поддерживать форму"):
        return await msg.answer("Выбери цель из списка")

    u = storage.get_user(msg.from_user.id)
    u["profile"][field] = val
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    await msg.answer(f"✅ {FORM_DISPLAY[field]} обновлено: {safe_md(val)}", reply_markup=MAIN_KB)
    await msg.answer(show_profile(u["profile"]), reply_markup=profile_menu())
    if field in PLAN_RELEVANT_FIELDS:
        await msg.answer("ℹ️ Это поле влияет на план. Обнови его в «🍽 План ИИ» → 🔄.")


# ---------- План ИИ (диета + тренировки текстом, сохраняется) ----------
def aiplan_kb() -> InlineKeyboardMarkup:
    return inline([[("🔄 Обновить план", "aiplan:gen")]])


async def gen_ai_plan(msg: Message, uid: int, profile: dict):
    plan = await with_thinking(msg, ai.build_plan, profile)
    u = storage.get_user(uid)
    u["ai_plan"] = plan
    storage.save_user(uid, u)
    await send_long(msg, plan)
    await msg.answer("👆 Это твой сохранённый план. Обновить — кнопкой ниже.", reply_markup=aiplan_kb())


@dp.message(F.text == "🍽 План ИИ")
async def ai_plan(msg: Message):
    u = storage.get_user(msg.from_user.id)
    if not u.get("profile"):
        return await msg.answer("Сначала заполни «📋 Анкета».")
    saved = u.get("ai_plan")
    if saved:
        await send_long(msg, saved)
        await msg.answer("👆 Сохранённый план. Чтобы пересоздать — кнопка ниже.", reply_markup=aiplan_kb())
    else:
        await gen_ai_plan(msg, msg.from_user.id, u["profile"])


@dp.callback_query(F.data == "aiplan:gen")
async def ai_plan_regen(cb: CallbackQuery):
    profile = storage.get_profile(cb.from_user.id)
    if not profile:
        return await cb.answer("Сначала заполни анкету", show_alert=True)
    await cb.answer("Генерирую заново…")
    await gen_ai_plan(cb.message, cb.from_user.id, profile)


# ---------- Мои тренировки (редактируемый план) ----------
def render_plan(plan: dict) -> str:
    if not plan:
        return "🏋️ *План тренировок пуст.*\nСгенерируй ИИ или добавь упражнения вручную."
    out = ["🏋️ *Твой план тренировок:*"]
    for day, exs in plan.items():
        out.append(f"\n📅 *{day}*")
        for i, e in enumerate(exs, 1):
            out.append(f"  {i}. {safe_md(e['name'])} — {safe_md(e['sets'])}, ⚖️ {safe_md(e['weight'])}")
    return "\n".join(out)


def plan_menu() -> InlineKeyboardMarkup:
    return inline([
        [("🤖 Сгенерировать ИИ", "plan:gen")],
        [("➕ Добавить упражнение", "plan:add"), ("✏️ Изменить", "plan:edit")],
        [("🗑 Очистить план", "plan:clear")],
    ])


@dp.message(F.text == "🏋️ Мои тренировки")
async def my_workouts(msg: Message):
    u = storage.get_user(msg.from_user.id)
    await msg.answer(render_plan(u["plan"]), reply_markup=plan_menu())


@dp.callback_query(F.data == "plan:gen")
async def plan_gen(cb: CallbackQuery):
    profile = storage.get_profile(cb.from_user.id)
    if not profile:
        return await cb.answer("Сначала заполни анкету", show_alert=True)
    await cb.answer()
    note = await cb.message.answer("⏳ Собираю план тренировок…")
    try:
        plan = await asyncio.to_thread(ai.build_plan_json, profile)
    except Exception as e:
        logging.exception("plan json")
        return await note.edit_text(f"⚠️ Не удалось: {e}")
    u = storage.get_user(cb.from_user.id)
    u["plan"] = plan
    storage.save_user(cb.from_user.id, u)
    await note.delete()
    await cb.message.answer(render_plan(plan), reply_markup=plan_menu())


@dp.callback_query(F.data == "plan:clear")
async def plan_clear(cb: CallbackQuery):
    u = storage.get_user(cb.from_user.id)
    u["plan"] = {}
    storage.save_user(cb.from_user.id, u)
    await cb.answer("План очищен")
    await cb.message.edit_text(render_plan({}), reply_markup=plan_menu())


@dp.callback_query(F.data == "plan:add")
async def plan_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    rows = [[(d, f"addday:{i}")] for i, d in enumerate(WEEKDAYS)]
    await cb.message.answer("В какой день добавить упражнение?", reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("addday:"))
async def plan_add_day(cb: CallbackQuery, state: FSMContext):
    day = WEEKDAYS[int(cb.data.split(":")[1])]
    await state.update_data(day=day)
    await state.set_state(Plan.name)
    await cb.answer()
    await cb.message.answer(f"📅 {day}. Название упражнения?")


@dp.message(Plan.name)
async def plan_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await state.set_state(Plan.sets)
    await msg.answer("Подходы x повторения (например 4x10)?")


@dp.message(Plan.sets)
async def plan_sets(msg: Message, state: FSMContext):
    await state.update_data(sets=msg.text)
    await state.set_state(Plan.weight)
    await msg.answer("Рабочий вес (например 60 кг или «свой вес»)?")


@dp.message(Plan.weight)
async def plan_weight(msg: Message, state: FSMContext):
    d = await state.get_data()
    u = storage.get_user(msg.from_user.id)
    u["plan"].setdefault(d["day"], []).append(
        {"name": d["name"], "sets": d["sets"], "weight": msg.text}
    )
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    await msg.answer("✅ Добавлено!")
    await msg.answer(render_plan(u["plan"]), reply_markup=plan_menu())


@dp.callback_query(F.data == "plan:edit")
async def plan_edit(cb: CallbackQuery):
    u = storage.get_user(cb.from_user.id)
    if not u["plan"]:
        return await cb.answer("План пуст", show_alert=True)
    await cb.answer()
    rows = [[(d, f"eday:{i}")] for i, d in enumerate(WEEKDAYS) if d in u["plan"]]
    await cb.message.answer("Выбери день:", reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("eday:"))
async def edit_day(cb: CallbackQuery):
    day = WEEKDAYS[int(cb.data.split(":")[1])]
    u = storage.get_user(cb.from_user.id)
    exs = u["plan"].get(day, [])
    await cb.answer()
    rows = [[(f"{i+1}. {e['name']}", f"eex:{WEEKDAYS.index(day)}:{i}")] for i, e in enumerate(exs)]
    await cb.message.answer(f"📅 {day}. Выбери упражнение:", reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("eex:"))
async def edit_ex(cb: CallbackQuery):
    _, di, idx = cb.data.split(":")
    await cb.answer()
    rows = [
        [("⚖️ Изменить вес", f"setw:{di}:{idx}"), ("🔁 Изменить подходы", f"sets:{di}:{idx}")],
        [("🗑 Удалить", f"del:{di}:{idx}")],
    ]
    await cb.message.answer("Что сделать?", reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("del:"))
async def del_ex(cb: CallbackQuery):
    _, di, idx = cb.data.split(":")
    day = WEEKDAYS[int(di)]
    u = storage.get_user(cb.from_user.id)
    try:
        u["plan"][day].pop(int(idx))
        if not u["plan"][day]:
            u["plan"].pop(day)
        storage.save_user(cb.from_user.id, u)
    except Exception:
        pass
    await cb.answer("Удалено")
    await cb.message.answer(render_plan(u["plan"]), reply_markup=plan_menu())


@dp.callback_query(F.data.startswith("setw:"))
async def set_weight_q(cb: CallbackQuery, state: FSMContext):
    _, di, idx = cb.data.split(":")
    await state.update_data(field="weight", di=di, idx=idx)
    await state.set_state(Plan.edit_value)
    await cb.answer()
    await cb.message.answer("Введи новый вес:")


@dp.callback_query(F.data.startswith("sets:"))
async def set_sets_q(cb: CallbackQuery, state: FSMContext):
    _, di, idx = cb.data.split(":")
    await state.update_data(field="sets", di=di, idx=idx)
    await state.set_state(Plan.edit_value)
    await cb.answer()
    await cb.message.answer("Введи новые подходы x повторения:")


@dp.message(Plan.edit_value)
async def apply_edit(msg: Message, state: FSMContext):
    d = await state.get_data()
    day = WEEKDAYS[int(d["di"])]
    u = storage.get_user(msg.from_user.id)
    try:
        u["plan"][day][int(d["idx"])][d["field"]] = msg.text
        storage.save_user(msg.from_user.id, u)
    except Exception:
        pass
    await state.clear()
    await msg.answer("✅ Обновлено!")
    await msg.answer(render_plan(u["plan"]), reply_markup=plan_menu())


# ---------- Пришёл в зал ----------
@dp.message(F.text == "✅ Пришёл в зал")
async def gym_checkin(msg: Message, state: FSMContext):
    await state.set_state(Misc.gym_note)
    await msg.answer(
        "💪 Отлично, отмечаю! Что сегодня качал?",
        reply_markup=kb(["Грудь", "Спина", "Ноги"], ["Руки", "Плечи", "Кардио"], ["Всё тело", "Пропустить"], ["⬅️ Назад"]),
    )


@dp.message(Misc.gym_note)
async def gym_note(msg: Message, state: FSMContext):
    note = "" if msg.text == "Пропустить" else msg.text
    u = storage.get_user(msg.from_user.id)
    u["visits"].append({"date": today(), "note": note})
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    total = len(u["visits"])
    await msg.answer(
        f"✅ Записал поход в зал ({date.today().strftime('%d.%m')})"
        + (f": {safe_md(note)}" if note else "") + f"\nВсего тренировок: {total} 🔥",
        reply_markup=MAIN_KB,
    )


# ---------- Статистика ----------
@dp.message(F.text == "📊 Статистика")
async def stats(msg: Message):
    u = storage.get_user(msg.from_user.id)
    visits = u["visits"]
    if not visits:
        return await msg.answer("Пока нет отметок. Жми «✅ Пришёл в зал» после тренировки.")
    # за последние 7/30 дней
    today_d = date.today()
    week = sum(1 for v in visits if (today_d - date.fromisoformat(v["date"])).days < 7)
    month = sum(1 for v in visits if (today_d - date.fromisoformat(v["date"])).days < 30)
    out = [
        "📊 *Статистика тренировок*",
        f"Всего: *{len(visits)}*  |  за 7 дней: *{week}*  |  за 30 дней: *{month}*\n",
        "*Последние походы:*",
    ]
    for v in visits[-10:][::-1]:
        d = date.fromisoformat(v["date"]).strftime("%d.%m")
        out.append(f"• {d} — {safe_md(v['note']) or 'тренировка'}")
    # вода за сегодня
    w = u["water"].get(today(), 0)
    out.append(f"\n💧 Вода сегодня: {w} мл")
    await msg.answer("\n".join(out))


# ---------- Вода / Белок ----------
def tracker_text(u: dict) -> str:
    s = u["settings"]
    w = u["water"].get(today(), 0)
    p = u["protein"].get(today(), 0)
    txt = [
        "💧 *Трекер за сегодня*",
        f"Вода: *{w}* / {s['water_goal']} мл",
    ]
    if s.get("protein_goal"):
        txt.append(f"Белок: *{p}* / {s['protein_goal']} г")
    else:
        txt.append(f"Белок: *{p}* г (цель не задана)")
    return "\n".join(txt)


def tracker_kb() -> InlineKeyboardMarkup:
    return inline([
        [("💧 +250 мл", "w:250"), ("💧 +500 мл", "w:500")],
        [("🥩 +20 г белка", "p:20"), ("🥩 +30 г белка", "p:30")],
        [("✏️ Своя вода", "add:water"), ("✏️ Свой белок", "add:protein")],
        [("🎯 Цель воды", "goal:water"), ("🎯 Цель белка", "goal:protein")],
    ])


@dp.message(F.text == "💧 Вода/Белок")
async def tracker(msg: Message):
    u = storage.get_user(msg.from_user.id)
    await msg.answer(tracker_text(u), reply_markup=tracker_kb())


@dp.callback_query(F.data.startswith("w:"))
async def add_water(cb: CallbackQuery):
    ml = int(cb.data.split(":")[1])
    u = storage.get_user(cb.from_user.id)
    u["water"][today()] = u["water"].get(today(), 0) + ml
    storage.save_user(cb.from_user.id, u)
    await cb.answer(f"+{ml} мл 💧")
    await cb.message.edit_text(tracker_text(u), reply_markup=tracker_kb())


@dp.callback_query(F.data.startswith("p:"))
async def add_protein(cb: CallbackQuery):
    g = int(cb.data.split(":")[1])
    u = storage.get_user(cb.from_user.id)
    u["protein"][today()] = u["protein"].get(today(), 0) + g
    storage.save_user(cb.from_user.id, u)
    await cb.answer(f"+{g} г белка 🥩")
    await cb.message.edit_text(tracker_text(u), reply_markup=tracker_kb())


@dp.callback_query(F.data.startswith("add:"))
async def custom_intake_q(cb: CallbackQuery, state: FSMContext):
    target = cb.data.split(":")[1]  # water / protein
    await state.update_data(intake_target=target)
    await state.set_state(Misc.custom_intake)
    await cb.answer()
    unit = "мл воды" if target == "water" else "г белка"
    await cb.message.answer(f"Сколько {unit} добавить? Введи число:", reply_markup=kb(["⬅️ Назад"]))


@dp.message(Misc.custom_intake)
async def custom_intake(msg: Message, state: FSMContext):
    if not msg.text.isdigit():
        return await msg.answer("Введи число, например 350")
    d = await state.get_data()
    u = storage.get_user(msg.from_user.id)
    key = "water" if d["intake_target"] == "water" else "protein"
    u[key][today()] = u[key].get(today(), 0) + int(msg.text)
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    unit = "мл воды 💧" if key == "water" else "г белка 🥩"
    await msg.answer(f"✅ Добавлено {msg.text} {unit}", reply_markup=MAIN_KB)
    await msg.answer(tracker_text(u), reply_markup=tracker_kb())


@dp.callback_query(F.data.startswith("goal:"))
async def set_goal_q(cb: CallbackQuery, state: FSMContext):
    target = cb.data.split(":")[1]
    await state.update_data(goal_target=target)
    await state.set_state(Misc.set_goal)
    await cb.answer()
    unit = "мл воды" if target == "water" else "г белка"
    await cb.message.answer(f"Введи дневную цель ({unit}), числом:")


@dp.message(Misc.set_goal)
async def set_goal(msg: Message, state: FSMContext):
    if not msg.text.isdigit():
        return await msg.answer("Введи число, например 2500")
    d = await state.get_data()
    u = storage.get_user(msg.from_user.id)
    key = "water_goal" if d["goal_target"] == "water" else "protein_goal"
    u["settings"][key] = int(msg.text)
    storage.save_user(msg.from_user.id, u)
    await state.clear()
    await msg.answer("✅ Цель сохранена!", reply_markup=MAIN_KB)
    await msg.answer(tracker_text(u), reply_markup=tracker_kb())


# ---------- Напоминания ----------
def rem_text(s: dict) -> str:
    on = lambda b: "✅ вкл" if b else "❌ выкл"
    days = ", ".join(d[:2] for d in s["workout_days"]) or "не заданы"
    return (
        "⏰ *Напоминания*\n\n"
        f"🏋️ Тренировки: {on(s['workout_reminder'])}\n"
        f"   дни: {days}, время: {s['workout_time']}\n"
        f"💊 Креатин: {on(s['creatine_reminder'])} ({s['creatine_time']})\n"
        f"💧 Вода (каждые 2 ч): {on(s['water_reminder'])}\n"
    )


def rem_kb(s: dict) -> InlineKeyboardMarkup:
    t = lambda b: "✅" if b else "❌"
    return inline([
        [(f"{t(s['workout_reminder'])} Тренировки", "r:workout")],
        [("📅 Дни тренировок", "rdays"), ("🕐 Время", "tt:workout")],
        [(f"{t(s['creatine_reminder'])} Креатин", "r:creatine"), ("🕐 Время", "tt:creatine")],
        [(f"{t(s['water_reminder'])} Вода", "r:water")],
    ])


@dp.message(F.text == "⏰ Напоминания")
async def rem_menu(msg: Message):
    u = storage.get_user(msg.from_user.id)
    await msg.answer(rem_text(u["settings"]), reply_markup=rem_kb(u["settings"]))


@dp.callback_query(F.data.startswith("r:"))
async def toggle_rem(cb: CallbackQuery):
    key = cb.data.split(":")[1] + "_reminder"
    u = storage.get_user(cb.from_user.id)
    u["settings"][key] = not u["settings"][key]
    storage.save_user(cb.from_user.id, u)
    reminders.reschedule_user(cb.from_user.id)
    await cb.answer("Готово")
    await cb.message.edit_text(rem_text(u["settings"]), reply_markup=rem_kb(u["settings"]))


@dp.callback_query(F.data == "rdays")
async def rem_days(cb: CallbackQuery):
    u = storage.get_user(cb.from_user.id)
    sel = u["settings"]["workout_days"]
    rows = [[("✅ " + d if d in sel else d, f"wday:{i}")] for i, d in enumerate(WEEKDAYS)]
    rows.append([("Готово", "wday:done")])
    await cb.answer()
    await cb.message.answer("Отметь дни тренировок:", reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("wday:"))
async def toggle_day(cb: CallbackQuery):
    val = cb.data.split(":")[1]
    u = storage.get_user(cb.from_user.id)
    if val == "done":
        reminders.reschedule_user(cb.from_user.id)
        await cb.answer("Сохранено")
        return await cb.message.edit_text(rem_text(u["settings"]), reply_markup=rem_kb(u["settings"]))
    day = WEEKDAYS[int(val)]
    sel = u["settings"]["workout_days"]
    if day in sel:
        sel.remove(day)
    else:
        sel.append(day)
    storage.save_user(cb.from_user.id, u)
    await cb.answer()
    rows = [[("✅ " + d if d in sel else d, f"wday:{i}")] for i, d in enumerate(WEEKDAYS)]
    rows.append([("Готово", "wday:done")])
    await cb.message.edit_reply_markup(reply_markup=inline(rows))


@dp.callback_query(F.data.startswith("tt:"))
async def set_time_q(cb: CallbackQuery, state: FSMContext):
    target = cb.data.split(":")[1]  # workout / creatine / sleep
    await state.update_data(time_target=target)
    await state.set_state(Misc.set_time)
    await cb.answer()
    await cb.message.answer("Введи время в формате ЧЧ:ММ (например 18:30):")


@dp.message(Misc.set_time)
async def set_time(msg: Message, state: FSMContext):
    try:
        datetime.strptime(msg.text.strip(), "%H:%M")
    except ValueError:
        return await msg.answer("Формат ЧЧ:ММ, например 18:30")
    d = await state.get_data()
    u = storage.get_user(msg.from_user.id)
    key = {"workout": "workout_time", "creatine": "creatine_time", "sleep": "sleep_time"}[d["time_target"]]
    u["settings"][key] = msg.text.strip()
    storage.save_user(msg.from_user.id, u)
    reminders.reschedule_user(msg.from_user.id)
    await state.clear()
    await msg.answer("✅ Время сохранено!", reply_markup=MAIN_KB)


# ---------- Сон ----------
def sleep_text(s: dict) -> str:
    on = "✅ вкл" if s["sleep_reminder"] else "❌ выкл"
    return (
        "😴 *Режим сна*\n\n"
        f"Напоминание отойти ко сну: {on}\n"
        f"Время: {s['sleep_time']}\n\n"
        "Сон 7–9 ч — главный фактор восстановления и роста мышц."
    )


def sleep_kb(s: dict) -> InlineKeyboardMarkup:
    t = "✅" if s["sleep_reminder"] else "❌"
    return inline([
        [(f"{t} Напоминание о сне", "r:sleep")],
        [("🕐 Время сна", "tt:sleep")],
        [("🛏 Ложусь спать", "sleep:now")],
    ])


@dp.message(F.text == "😴 Сон")
async def sleep_menu(msg: Message):
    u = storage.get_user(msg.from_user.id)
    await msg.answer(sleep_text(u["settings"]), reply_markup=sleep_kb(u["settings"]))


@dp.callback_query(F.data == "sleep:now")
async def sleep_now(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("🌙 Отличное решение! Спокойной ночи, восстанавливайся. До завтра 💤")


# ---------- Оценка формы ----------
@dp.message(F.text == "📸 Оценить форму")
async def ask_photo(msg: Message):
    await msg.answer("Пришли фото в полный рост — оценю телосложение и подскажу, что качать 💪")


@dp.message(F.photo)
async def on_photo(msg: Message):
    file = await bot.get_file(msg.photo[-1].file_id)
    buf = await bot.download_file(file.file_path)
    image_bytes = buf.read()
    profile = storage.get_profile(msg.from_user.id)
    try:
        result = await with_thinking(msg, ai.analyze_photo, image_bytes, profile)
    except Exception as e:
        logging.exception("vision")
        return await msg.answer(f"⚠️ Не удалось проанализировать фото: {e}")
    await send_long(msg, result)


# ---------- Чат с тренером (с памятью) ----------
@dp.message(F.text == "💬 Тренер")
async def chat_start(msg: Message, state: FSMContext):
    await state.set_state(Form.chat)
    await msg.answer(
        "Задай любой вопрос про тренировки, питание, восстановление. Я помню наш диалог.",
        reply_markup=kb(["⬅️ Назад"]),
    )


@dp.message(Form.chat)
async def chat_answer(msg: Message, state: FSMContext):
    u = storage.get_user(msg.from_user.id)
    history = u["history"][-12:]
    try:
        answer = await with_thinking(msg, ai.ask_coach, msg.text, u["profile"], history)
    except Exception as e:
        logging.exception("chat")
        return await msg.answer(f"⚠️ Ошибка: {e}")
    # сохраняем память
    u["history"].append({"role": "user", "content": msg.text})
    u["history"].append({"role": "assistant", "content": answer})
    u["history"] = u["history"][-20:]
    storage.save_user(msg.from_user.id, u)
    await send_long(msg, answer)


# ---------- Фолбэк ----------
@dp.message(StateFilter(None))
async def fallback(msg: Message):
    await msg.answer("Выбери действие на клавиатуре ниже 👇", reply_markup=MAIN_KB)


# ---------- Глобальный перехват ошибок (бот не падает) ----------
@dp.errors()
async def on_error(event: ErrorEvent):
    logging.exception("Необработанная ошибка", exc_info=event.exception)
    upd = event.update
    try:
        if upd.callback_query:
            await upd.callback_query.answer("⚠️ Не получилось, попробуй ещё раз", show_alert=False)
        elif upd.message:
            await upd.message.answer(
                "⚠️ Упс, что-то пошло не так. Нажми /start и попробуй снова.",
                reply_markup=MAIN_KB,
            )
    except Exception:
        pass
    return True  # ошибка обработана — бот продолжает работать


async def main():
    if not os.getenv("BOT_TOKEN") or not os.getenv("OPENROUTER_BASE_URL"):
        raise SystemExit("Заполни BOT_TOKEN и OPENROUTER_BASE_URL в .env")
    await bot.delete_webhook(drop_pending_updates=True)
    reminders.start(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
