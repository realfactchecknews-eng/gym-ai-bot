# 💪 Gym Bot — ИИ-тренер в Telegram

Телеграм-бот, который по анкете подбирает **диету** и **программу тренировок**,
а также **оценивает форму по фото** и советует, что подкачать. ИИ — через OpenRouter.

> Бот в проде: **@mellgym_bot** (название MELLGYM). Хостинг — BotHost.

## Возможности
- 📋 **Анкета**: пол, возраст, рост, вес, уровень, частота, место, цель.
- 🍽 **План ИИ**: расчёт калорий/БЖУ, меню на день, сплит тренировок.
- 🏋️ **Мои тренировки**: редактируемый план — генерация ИИ, добавление/изменение
  упражнений, веса и подходов, сохраняется и правится в любой момент.
- ✅ **Пришёл в зал**: чек-ин с пометкой что качал.
- 📊 **Статистика**: походы за 7/30 дней, история, вода за день.
- 💧 **Вода/Белок**: трекер с дневными целями.
- ⏰ **Напоминания**: тренировки (по дням и времени), креатин, вода.
- 😴 **Сон**: напоминание отойти ко сну.
- 📸 **Оценка формы по фото**: vision-модель разбирает телосложение.
- 💬 **Тренер**: чат с памятью диалога и учётом анкеты.

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
3. В переменные окружения добавить `BOT_TOKEN`, `OPENROUTER_BASE_URL`, `PROXY_SECRET`,
   `DATABASE_URL` (и при желании `TEXT_MODEL` / `VISION_MODEL`). Ключа OpenRouter тут нет.

## База данных
Данные (анкеты, планы, статистика, настройки) хранятся в **Postgres** —
задай `DATABASE_URL`. Без него бот пишет в локальный `data.json` (для разработки).

Бесплатный Postgres за минуту — [Neon](https://neon.tech):
1. Создай проект → скопируй **Connection string** (`postgresql://...`).
2. Вставь в `DATABASE_URL`. Таблица `users` создаётся автоматически при старте.

`Procfile` уже настроен (`worker: python bot.py`).

## Структура
```
bot.py          # хендлеры, FSM-анкета, клавиатуры, все вкладки
ai.py           # OpenRouter (OpenAI SDK): план, JSON-план, анализ фото, чат с памятью
storage.py      # данные: Postgres (DATABASE_URL) либо JSON-файл (fallback)
reminders.py    # APScheduler: напоминания тренировки/креатин/вода/сон (TZ Europe/Moscow)
worker/README.md# код и деплой Cloudflare-воркера (прокси к OpenRouter)
requirements.txt
Procfile        # worker: python bot.py
.env.example
```

## 🛠 Шпаргалка по инфраструктуре

**Архитектура:**
```
Telegram ──▶ Бот (BotHost, python bot.py)
                ├─▶ Cloudflare Worker ──▶ OpenRouter (ключ спрятан в воркере)
                └─▶ Neon Postgres (данные пользователей, jsonb)
```

**Переменные окружения (BotHost):**
| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен @BotFather |
| `OPENROUTER_BASE_URL` | URL Cloudflare-воркера (без `/chat/completions`) |
| `PROXY_SECRET` | общий пароль бот ↔ воркер |
| `TEXT_MODEL` | `google/gemini-2.5-flash` |
| `VISION_MODEL` | `google/gemini-2.5-flash` |
| `DATABASE_URL` | строка подключения Neon Postgres |

> ⚠️ Ключ OpenRouter (`OPENROUTER_API_KEY`) и `PROXY_SECRET` лежат **только в секретах
> Cloudflare-воркера** и переменных BotHost — в репозиторий их не коммитим.

**Cloudflare Worker** (`gym-openrouter-proxy`): секреты `OPENROUTER_API_KEY` + `PROXY_SECRET`,
проверяет заголовок `X-Proxy-Secret`, подставляет ключ, проксирует на `openrouter.ai/api/v1`.
Деплой и код — в [worker/README.md](worker/README.md).

**Модели:** OpenRouter, слаги Gemini — версия `2.5` (старые `gemini-2.0`/`flash-1.5` удалены).
Дешевле — `google/gemini-2.5-flash-lite`. Vision и текст обслуживает одна и та же модель.

**Хранилище:** Neon free — 0.5 ГБ (~25k юзеров). Фото НЕ сохраняются (анализ в памяти).
История чата ограничена 20 сообщениями. План кэшируется, регенерится только по кнопке.

**Заметки по эксплуатации:**
- Ответы ИИ шлются с `parse_mode=None` (Markdown от модели ломал Telegram-парсер).
- `httpx` запинен на `0.27.2` (0.28+ несовместим с openai из-за аргумента `proxies`).
- JS-воркер вынесен из репо в README, иначе BotHost пытался запускать его через Node.

> ⚠️ Рекомендации носят информационный характер. При проблемах со здоровьем —
> консультируйтесь с врачом.
