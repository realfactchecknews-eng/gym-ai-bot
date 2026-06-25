"""Хранилище данных пользователей в JSON-файле."""
import json
import os
from copy import deepcopy
from threading import Lock

_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_lock = Lock()

DEFAULT = {
    "profile": {},          # анкета
    "history": [],          # память диалога с тренером [{role, content}]
    "plan": {},             # план тренировок {день: [{name, sets, weight}]}
    "visits": [],           # походы в зал [{date, note}]
    "water": {},            # вода по дням {date: ml}
    "protein": {},          # белок по дням {date: g}
    "settings": {
        "workout_days": [],          # ["Понедельник", ...]
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


def _read() -> dict:
    if not os.path.exists(_FILE):
        return {}
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict) -> None:
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(user_id: int) -> dict:
    """Возвращает данные пользователя, дополняя недостающие поля дефолтами."""
    data = _read()
    u = data.get(str(user_id), {})
    merged = deepcopy(DEFAULT)
    merged.update({k: v for k, v in u.items() if k != "settings"})
    merged["settings"] = {**DEFAULT["settings"], **u.get("settings", {})}
    return merged


def save_user(user_id: int, user: dict) -> None:
    with _lock:
        data = _read()
        data[str(user_id)] = user
        _write(data)


def update_user(user_id: int, **fields) -> dict:
    with _lock:
        data = _read()
        u = data.get(str(user_id)) or deepcopy(DEFAULT)
        u.update(fields)
        data[str(user_id)] = u
        _write(data)
        return u


def all_user_ids() -> list[int]:
    return [int(k) for k in _read().keys()]


# --- обратная совместимость со старым кодом ---
def save_profile(user_id: int, profile: dict) -> None:
    u = get_user(user_id)
    u["profile"] = profile
    save_user(user_id, u)


def get_profile(user_id: int) -> dict | None:
    p = get_user(user_id).get("profile")
    return p or None
