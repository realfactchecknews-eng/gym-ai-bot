"""Хранилище данных пользователей.

Бэкенды:
  • Postgres (если задан DATABASE_URL) — таблица users(uid bigint PK, data jsonb).
  • JSON-файл (fallback для локальной разработки).
Интерфейс одинаковый: get_user / save_user / update_user / all_user_ids.
"""
import json
import os
from copy import deepcopy
from threading import Lock

DEFAULT = {
    "profile": {},          # анкета
    "history": [],          # память диалога [{role, content}]
    "plan": {},             # план тренировок {день: [{name, sets, weight}]}
    "visits": [],           # походы в зал [{date, note}]
    "water": {},            # вода по дням {date: ml}
    "protein": {},          # белок по дням {date: g}
    "settings": {
        "workout_days": [],
        "workout_time": "18:00",
        "workout_reminder": False,
        "creatine_reminder": False,
        "creatine_time": "09:00",
        "water_goal": 2500,
        "water_reminder": False,
        "protein_goal": 0,
        "sleep_time": "23:00",
        "sleep_reminder": False,
    },
}

_lock = Lock()
DATABASE_URL = os.getenv("DATABASE_URL")


def _merge(u: dict) -> dict:
    """Дополняет данные пользователя недостающими полями из DEFAULT."""
    merged = deepcopy(DEFAULT)
    merged.update({k: v for k, v in u.items() if k != "settings"})
    merged["settings"] = {**DEFAULT["settings"], **u.get("settings", {})}
    return merged


# ====================== Postgres-бэкенд ======================
if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import SimpleConnectionPool

    # Neon/большинство облачных Postgres требуют sslmode=require
    if "sslmode=" not in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL += f"{sep}sslmode=require"

    _pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL)

    def _init():
        conn = _pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS users ("
                    "uid BIGINT PRIMARY KEY, data JSONB NOT NULL)"
                )
            conn.commit()
        finally:
            _pool.putconn(conn)

    _init()

    def get_user(user_id: int) -> dict:
        conn = _pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM users WHERE uid = %s", (user_id,))
                row = cur.fetchone()
            return _merge(row[0] if row else {})
        finally:
            _pool.putconn(conn)

    def save_user(user_id: int, user: dict) -> None:
        conn = _pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (uid, data) VALUES (%s, %s) "
                    "ON CONFLICT (uid) DO UPDATE SET data = EXCLUDED.data",
                    (user_id, psycopg2.extras.Json(user)),
                )
            conn.commit()
        finally:
            _pool.putconn(conn)

    def all_user_ids() -> list[int]:
        conn = _pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT uid FROM users")
                return [r[0] for r in cur.fetchall()]
        finally:
            _pool.putconn(conn)

# ====================== JSON-бэкенд ======================
else:
    _FILE = os.path.join(os.path.dirname(__file__), "data.json")

    def _read() -> dict:
        if not os.path.exists(_FILE):
            return {}
        with open(_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_user(user_id: int) -> dict:
        return _merge(_read().get(str(user_id), {}))

    def save_user(user_id: int, user: dict) -> None:
        with _lock:
            data = _read()
            data[str(user_id)] = user
            with open(_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def all_user_ids() -> list[int]:
        return [int(k) for k in _read().keys()]


# ====================== Общие хелперы ======================
def update_user(user_id: int, **fields) -> dict:
    with _lock:
        u = get_user(user_id)
        u.update(fields)
        save_user(user_id, u)
        return u


def save_profile(user_id: int, profile: dict) -> None:
    u = get_user(user_id)
    u["profile"] = profile
    save_user(user_id, u)


def get_profile(user_id: int) -> dict | None:
    return get_user(user_id).get("profile") or None
