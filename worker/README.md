# Cloudflare Worker — прокси к OpenRouter

Прячет ключ OpenRouter: бот ходит на воркер, ключ лежит в секретах Cloudflare.

> ⚠️ Этот воркер деплоится **в Cloudflare**, а НЕ на BotHost. Поэтому исходник
> вынесен в этот README (как код-блок), чтобы хостинг бота случайно не пытался
> запускать его через Node. Боту нужен только URL воркера и `PROXY_SECRET`.

## Деплой через сайт Cloudflare
1. dash.cloudflare.com → **Workers & Pages** → **Create Worker**.
2. Имя `gym-openrouter-proxy` → Deploy → **Edit code** → вставить код ниже → Deploy.
3. **Settings → Variables and Secrets** → добавить два Secret:
   - `OPENROUTER_API_KEY` = `sk-or-...`
   - `PROXY_SECRET` = любой пароль
4. Скопировать URL вида `https://gym-openrouter-proxy.<аккаунт>.workers.dev`.

## Код воркера
```javascript
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Only POST", { status: 405 });
    }
    if (env.PROXY_SECRET && request.headers.get("X-Proxy-Secret") !== env.PROXY_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    const url = new URL(request.url);
    const target = "https://openrouter.ai/api/v1" + url.pathname;
    const headers = new Headers({
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
      "HTTP-Referer": "https://t.me/your_gym_bot",
      "X-Title": "Gym AI Bot",
    });
    const resp = await fetch(target, { method: "POST", headers, body: request.body });
    return new Response(resp.body, {
      status: resp.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Прописать в боте (.env / BotHost)
```
OPENROUTER_BASE_URL=https://gym-openrouter-proxy.<аккаунт>.workers.dev
PROXY_SECRET=<тот же пароль>
```

В коде/на BotHost ключа OpenRouter нет — только URL воркера и общий пароль.
