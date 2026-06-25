"""Обёртка над OpenRouter (через Cloudflare-воркер): план и анализ формы по фото.

Бот не знает ключ OpenRouter — он ходит на воркер (OPENROUTER_BASE_URL),
а ключ подставляется внутри воркера. Доступ к воркеру защищён PROXY_SECRET.
"""
import os
import json
import base64
from openai import OpenAI

# Базовый URL = твой Cloudflare-воркер (он же эмулирует /chat/completions).
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
PROXY_SECRET = os.getenv("PROXY_SECRET", "")

# Ключ боту не нужен (его держит воркер). Если ходишь напрямую в OpenRouter —
# задай OPENROUTER_API_KEY. Для SDK нужно непустое значение, поэтому "proxy".
API_KEY = os.getenv("OPENROUTER_API_KEY", "proxy")

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    default_headers={"X-Proxy-Secret": PROXY_SECRET} if PROXY_SECRET else {},
)

# Нормальные модели OpenRouter (меняй в .env при желании)
TEXT_MODEL = os.getenv("TEXT_MODEL", "google/gemini-2.5-flash")
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-2.5-flash")

SYSTEM_COACH = (
    "Ты — профессиональный фитнес-тренер и нутрициолог. "
    "Отвечаешь по-русски, развёрнуто, но по делу: структурируй ответ заголовками, "
    "списками и эмодзи, давай конкретные цифры (вес, подходы, граммы, калории). "
    "Помни предыдущие сообщения диалога и данные анкеты клиента, давай персональные "
    "рекомендации. Не выдумывай медицинских диагнозов и при серьёзных проблемах "
    "со здоровьем советуешь обратиться к врачу."
)


def build_plan(profile: dict) -> str:
    """Подбирает диету и программу тренировок по анкете пользователя."""
    prompt = (
        "Составь для человека персональный план. Данные анкеты:\n"
        f"• Пол: {profile.get('sex')}\n"
        f"• Возраст: {profile.get('age')}\n"
        f"• Рост: {profile.get('height')} см\n"
        f"• Вес: {profile.get('weight')} кг\n"
        f"• Уровень подготовки: {profile.get('level')}\n"
        f"• Тренировок в неделю: {profile.get('days')}\n"
        f"• Где тренируется: {profile.get('place')}\n"
        f"• Цель: {profile.get('goal')}\n\n"
        "Выдай ответ в формате:\n"
        "1) 🎯 Краткий разбор цели и расчёт калорий/БЖУ (формула Миффлина-Сан Жеора).\n"
        "2) 🍽 Диета: примерное меню на день с граммовками и список продуктов.\n"
        "3) 🏋️ Программа тренировок: сплит по дням недели с упражнениями, "
        "подходами и повторениями.\n"
        "4) 💡 3-5 советов по прогрессу и восстановлению.\n"
        "Будь конкретным."
    )
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_COACH},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return resp.choices[0].message.content


def build_plan_json(profile: dict) -> dict:
    """Генерирует структурированный план тренировок (для редактирования)."""
    days = profile.get("days", "3")
    prompt = (
        f"Составь сплит тренировок на {days} дней в неделю для клиента: "
        f"{profile.get('sex')}, {profile.get('age')} лет, {profile.get('weight')} кг, "
        f"уровень {profile.get('level')}, цель {profile.get('goal')}, "
        f"место {profile.get('place')}.\n"
        "Верни СТРОГО JSON без пояснений в формате: "
        '{"Понедельник": [{"name":"Жим лёжа","sets":"4x10","weight":"60 кг"}], ...}. '
        "Дни недели — ключи на русском, у каждого упражнения name, sets, weight. "
        "weight — стартовый рабочий вес или 'свой вес' для упражнений без отягощения."
    )
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": "Ты фитнес-тренер. Отвечаешь только валидным JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def analyze_photo(image_bytes: bytes, profile: dict | None = None) -> str:
    """Оценивает телосложение по фото и советует, что качать."""
    b64 = base64.b64encode(image_bytes).decode()
    goal = profile.get("goal") if profile else "набор формы"
    text = (
        "Оцени телосложение человека на фото как фитнес-тренер. "
        f"Его цель: {goal}. "
        "Дай: 1) общую оценку формы и осанки, 2) какие мышечные группы "
        "отстают и их стоит подтянуть, 3) конкретные упражнения для них, "
        "4) примерный совет по жиру/рельефу. Деликатно и мотивирующе, по-русски."
    )
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        temperature=0.6,
        max_tokens=1024,
    )
    return resp.choices[0].message.content


def ask_coach(question: str, profile: dict | None = None, history: list | None = None) -> str:
    """Свободный вопрос тренеру с учётом анкеты и истории диалога (память)."""
    ctx = ""
    if profile:
        ctx = (
            f"Анкета клиента: пол {profile.get('sex')}, возраст {profile.get('age')}, "
            f"рост {profile.get('height')} см, вес {profile.get('weight')} кг, "
            f"уровень {profile.get('level')}, цель {profile.get('goal')}.\n"
            "Учитывай это при ответах."
        )
    messages = [{"role": "system", "content": SYSTEM_COACH + "\n" + ctx}]
    if history:
        messages.extend(history)  # [{role, content}, ...] — память диалога
    messages.append({"role": "user", "content": question})
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
    )
    return resp.choices[0].message.content
