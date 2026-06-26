# 🔥 MASSAGYM — ИИ-тренер в Telegram

Телеграм-бот, который по анкете подбирает **диету** и **программу тренировок**, ведёт редактируемый план, считает воду/белок, напоминает о тренировках и **оценивает форму по фото**. ИИ — через OpenRouter.

> Бот в проде: **massagym**. Хостинг — BotHost. Стабильная версия — тег `v1.0-stable`.

## Возможности

- 📋 **Анкета**: пол, возраст, рост, вес, уровень, частота, место, цель. Запоминается — повторно можно **изменить любое поле** без перезаполнения.
- 🍽 **План ИИ**: расчёт калорий/БЖУ, меню на день, сплит тренировок.
- 🏋️ **Мои тренировки**: редактируемый план — генерация ИИ, добавление/изменение упражнений, веса и подходов.
- ✅ **Пришёл в зал**: чек-ин с пометкой что качал.
- 📊 **Статистика**: походы за 7/30 дней, **серия дней подряд (streak)**, история, вода за день.
- 💧 **Вода/Белок**: трекер с дневными целями.
- ⏰ **Напоминания**: тренировки (по дням и времени), креатин, вода.
- 😴 **Сон**: напоминание отойти ко сну.
- 📸 **Оценка формы по фото**: vision-модель разбирает телосложение.
- 💬 **Тренер**: чат с памятью диалога и учётом анкеты.

## Технологии

- [aiogram 3](https://docs.aiogram.dev/) — Telegram-бот на polling.
- [OpenRouter](https://openrouter.ai/) — доступ к топовым моделям (`google/gemini-2.5-flash` и др.), совместим с OpenAI SDK.
- [Cloudflare Worker](worker/README.md) — прокси, который **прячет ключ OpenRouter**: бот ходит на воркер, ключ хранится в секретах Cloudflare.
Бот (BotHost) ──X-Proxy-Secret──▶ Cloudflare Worker ──OPENROUTER_API_KEY──▶ OpenRouter


## Запуск локально

1. Задеплой воркер — см. [worker/README.md](worker/README.md).
2. Затем бот:

```bash
pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN, OPENROUTER_BASE_URL, PROXY_SECRET
python bot.py
Токен бота — у @BotFather, ключ OpenRouter — на openrouter.ai/keys (живёт только в воркере).

Хостинг на BotHost
Залить репозиторий или папку проекта.
Команда запуска: python bot.py.
В переменные окружения добавить BOT_TOKEN, OPENROUTER_BASE_URL, PROXY_SECRET, DATABASE_URL (и при желании TEXT_MODEL / VISION_MODEL). Ключа OpenRouter тут нет.
База данных
Данные (анкеты, планы, статистика, настройки) хранятся в Postgres — задай DATABASE_URL. Без него бот пишет в локальный data.json (для разработки).

Бесплатный Postgres за минуту — Neon:

Создай проект → скопируй Connection string (postgresql://...).
Вставь в DATABASE_URL. Таблица users создаётся автоматически при старте.
Procfile уже настроен (worker: python bot.py).

Структура
bot.py          # хендлеры, FSM-анкета с прогрессом, умный профиль (показ + редактирование полей), клавиатуры, все вкладки
ai.py           # OpenRouter (OpenAI SDK): план, JSON-план, анализ фото, чат с памятью
storage.py      # данные: Postgres (DATABASE_URL) либо JSON-файл (fallback)
reminders.py    # APScheduler: напоминания тренировки/креатин/вода/сон (TZ Europe/Moscow)
worker/README.md# код и деплой Cloudflare-воркера (прокси к OpenRouter)
requirements.txt
Procfile        # worker: python bot.py
.env.example
🛠 Шпаргалка по инфраструктуре
Архитектура:

Telegram ──▶ Бот (BotHost, python bot.py)
                ├─▶ Cloudflare Worker ──▶ OpenRouter (ключ спрятан в воркере)
                └─▶ Neon Postgres (данные пользователей, jsonb)
Переменные окружения (BotHost):

Переменная	Назначение
BOT_TOKEN	токен @BotFather
OPENROUTER_BASE_URL	URL Cloudflare-воркера (без /chat/completions)
PROXY_SECRET	общий пароль бот ↔ воркер
TEXT_MODEL	google/gemini-2.5-flash
VISION_MODEL	google/gemini-2.5-flash
DATABASE_URL	строка подключения Neon Postgres
⚠️ Ключ OpenRouter (OPENROUTER_API_KEY) и PROXY_SECRET лежат только в секретах Cloudflare-воркера и переменных BotHost — в репозиторий их не коммитим.

Cloudflare Worker (gym-openrouter-proxy): секреты OPENROUTER_API_KEY + PROXY_SECRET, проверяет заголовок X-Proxy-Secret, подставляет ключ, проксирует на openrouter.ai/api/v1. Деплой и код — в worker/README.md.

Модели: OpenRouter, слаги Gemini — версия 2.5 (старые gemini-2.0/flash-1.5 удалены). Vision и текст обслуживает одна и та же модель.

Хранилище: Neon free — 0.5 ГБ (~25k юзеров). Фото НЕ сохраняются (анализ в памяти). История чата ограничена 20 сообщениями. План кэшируется, регенерится только по кнопке.

Заметки по эксплуатации:

Ответы ИИ шлются с parse_mode=None (Markdown от модели ломал Telegram-парсер).
httpx запинен на 0.27.2 (0.28+ несовместим с openai из-за аргумента proxies).
JS-воркер вынесен из репо в README, иначе BotHost пытался запускать его через Node.
Умный профиль: при повторном «📋 Анкета» бот показывает сводку и предлагает изменить конкретное поле вместо перезаполнения.
Валидация анкеты: диапазоны (возраст 10-100, рост 100-250, вес 30-300), кнопки «⬅️ Назад» на каждом шаге, прогресс «Шаг X из 8».
Фото: не анализируются во время заполнения анкеты/редактирования (защита от случайных нажатий).
🤖 Как сменить модель ИИ
Модель задаётся переменными окружения — код менять не надо.

Переменная	За что отвечает
TEXT_MODEL	планы, чат с тренером (текст)
VISION_MODEL	анализ формы по фото (нужна модель с поддержкой зрения!)
Чтобы сменить модель — поменяй значение переменной на BotHost и сделай Redeploy.

Рабочие слаги OpenRouter (актуальные):

Слаг	Текст	Фото	Цена (вход/выход за 1М)
google/gemini-2.5-flash	✅	✅	
0.30
/
0.30/2.50 — рекомендация
google/gemini-2.5-flash-lite	✅	✅	
0.10
/
0.10/0.40 — дешевле
google/gemini-2.5-pro	✅	✅	
1.25
/
1.25/10 — максимум качества
openai/gpt-4o-mini	✅	✅	
0.15
/
0.15/0.60
anthropic/claude-3.7-sonnet	✅	✅	дороже, топ-планы
Полный каталог и цены: openrouter.ai/models.

⚠️ Частая ошибка: слаги вида gemini-2.0-flash-001 или gemini-flash-1.5 удалены из OpenRouter и дают ошибку No endpoints found (404). Используй версии 2.5. Проверить модель можно curl-ом:

curl -X POST $OPENROUTER_BASE_URL/chat/completions \
  -H "Content-Type: application/json" -H "X-Proxy-Secret: $PROXY_SECRET" \
  -d '{"model":"google/gemini-2.5-flash","messages":[{"role":"user","content":"тест"}]}'
Если в ответе choices — модель рабочая; если error — поменяй слаг.

Можно развести задачи, например дешёвый чат + качественные планы:

TEXT_MODEL=google/gemini-2.5-flash
VISION_MODEL=google/gemini-2.5-flash-lite
🔖 Версии и бэкап
Стабильные версии помечаются git-тегами.

v1.0-stable — полный функционал: умный профиль с редактированием полей, планы, чек-ин, статистика со streak, напоминания, трекеры воды/белка, оценка формы, чат с памятью; OpenRouter через воркер, Neon Postgres.
Откат к рабочей версии:

git checkout v1.0-stable
