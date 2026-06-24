/**
 * Cloudflare Worker — прокси к OpenRouter.
 * Прячет OPENROUTER_API_KEY: бот обращается к воркеру, а ключ хранится
 * в секретах Cloudflare и подставляется здесь.
 *
 * Секреты (wrangler secret put ...):
 *   OPENROUTER_API_KEY — ключ OpenRouter (sk-or-...)
 *   PROXY_SECRET       — общий пароль между ботом и воркером
 */
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Only POST", { status: 405 });
    }

    // Простая защита: бот шлёт заголовок X-Proxy-Secret
    if (env.PROXY_SECRET && request.headers.get("X-Proxy-Secret") !== env.PROXY_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }

    const url = new URL(request.url);
    // Пробрасываем путь как есть: /chat/completions, /models и т.д.
    const target = "https://openrouter.ai/api/v1" + url.pathname;

    const headers = new Headers({
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
      "HTTP-Referer": "https://t.me/your_gym_bot",
      "X-Title": "Gym AI Bot",
    });

    const resp = await fetch(target, {
      method: "POST",
      headers,
      body: request.body,
    });

    // Отдаём ответ обратно боту
    return new Response(resp.body, {
      status: resp.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
