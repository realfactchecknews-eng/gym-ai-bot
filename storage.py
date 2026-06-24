"""Простое хранилище профилей в JSON-файле."""
import json
import os
from threading import Lock

_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_lock = Lock()


def _read() -> dict:
    if not os.path.exists(_FILE):
        return {}
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(user_id: int, profile: dict) -> None:
    with _lock:
        data = _read()
        data[str(user_id)] = profile
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def get_profile(user_id: int) -> dict | None:
    return _read().get(str(user_id))
