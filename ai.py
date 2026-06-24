"""Обёртка над Groq: генерация плана и анализ формы по фото."""
import os
import base64
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Текстовая модель для планов
TEXT_MODEL = "llama-3.3-70b-versatile"
# Vision-модель для анализа фото
VISION_MODEL = "llama-3.2-90b-vision-preview"

SYSTEM_COACH = (
    "Ты — профессиональный фитнес-тренер и нутрициолог. "
    "Отвечаешь по-русски, чётко, структурированно, с эмодзи и заголовками. "
    "Даёшь практичные, безопасные рекомендации. Не выдумывай медицинских диагнозов "
    "и при серьёзных проблемах со здоровьем советуешь обратиться к врачу."
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
        max_tokens=2048,
    )
    return resp.choices[0].message.content


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


def ask_coach(question: str, profile: dict | None = None) -> str:
    """Свободный вопрос тренеру с учётом анкеты."""
    ctx = ""
    if profile:
        ctx = (
            f"Профиль пользователя: пол {profile.get('sex')}, возраст {profile.get('age')}, "
            f"рост {profile.get('height')} см, вес {profile.get('weight')} кг, "
            f"цель {profile.get('goal')}.\n"
        )
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_COACH},
            {"role": "user", "content": ctx + question},
        ],
        temperature=0.7,
        max_tokens=1200,
    )
    return resp.choices[0].message.content
