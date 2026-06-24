# 💪 Gym Bot — ИИ-тренер в Telegram

Телеграм-бот, который по анкете подбирает **диету** и **программу тренировок**,
а также **оценивает форму по фото** и советует, что подкачать. Под капотом — ИИ Groq.

## Возможности
- 📋 **Анкета**: пол, возраст, рост, вес, уровень, частота, место, цель.
- 💪 **План**: расчёт калорий/БЖУ, меню на день, сплит тренировок с подходами.
- 📸 **Оценка формы по фото**: vision-модель разбирает телосложение и осанку.
- 💬 **Чат с тренером**: свободные вопросы про питание и тренировки.

## Технологии
- [aiogram 3](https://docs.aiogram.dev/) — Telegram-бот на polling.
- [OpenRouter](https://openrouter.ai/) — доступ к топовым моделям (`gpt-4o-mini` и др.),
  совместим с OpenAI SDK.
- [Cloudflare Worker](worker/) — прокси, который **прячет ключ OpenRouter**: бот ходит
  на воркер, ключ хранится в секретах Cloudflare.

```
Бот (BotHost)  ──X-Proxy-Secret──▶  Cloudflare Worker  ──OPENROUTER_API_KEY──▶  OpenRouter
```

## Запуск локально
1. Задеплой воркер — см. [worker/README.md](worker/README.md).
2. Затем бот:
```bash
pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN, OPENROUTER_BASE_URL, PROXY_SECRET
python bot.py
```

Токен бота — у [@BotFather](https://t.me/BotFather), ключ OpenRouter — на
[openrouter.ai/keys](https://openrouter.ai/keys) (живёт только в воркере).

## Хостинг на BotHost
1. Залить репозиторий или папку проекта.
2. Команда запуска: `python bot.py`.
3. В переменные окружения добавить `BOT_TOKEN`, `OPENROUTER_BASE_URL`, `PROXY_SECRET`
   (и при желании `TEXT_MODEL` / `VISION_MODEL`). Ключа OpenRouter тут нет.

`Procfile` уже настроен (`worker: python bot.py`).

## Структура
```
bot.py          # хендлеры, FSM-анкета, клавиатуры
ai.py           # обёртка над Groq: план, анализ фото, чат
storage.py      # хранение профилей в data.json
requirements.txt
Procfile
.env.example
```

> ⚠️ Рекомендации носят информационный характер. При проблемах со здоровьем —
> консультируйтесь с врачом.
