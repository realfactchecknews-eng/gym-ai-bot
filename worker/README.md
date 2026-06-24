# Cloudflare Worker — прокси к OpenRouter

Прячет ключ OpenRouter: бот ходит на воркер, ключ лежит в секретах Cloudflare.

## Деплой
```bash
npm i -g wrangler
wrangler login
cd worker

# секреты (в файлы не попадают)
wrangler secret put OPENROUTER_API_KEY   # sk-or-...
wrangler secret put PROXY_SECRET         # придумай любой пароль

wrangler deploy
```

После деплоя получишь URL вида:
`https://gym-openrouter-proxy.<твой-аккаунт>.workers.dev`

## Прописать в боте (.env)
```
OPENROUTER_BASE_URL=https://gym-openrouter-proxy.<аккаунт>.workers.dev
PROXY_SECRET=<тот же пароль>
```

Бот будет дёргать `OPENROUTER_BASE_URL/chat/completions`, воркер подставит ключ.
В коде/на BotHost ключа OpenRouter нет — только URL воркера и общий пароль.
