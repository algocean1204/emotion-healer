"""설정: 파일 기본값 + 사용자별 Postgres."""

from __future__ import annotations

import json
from pathlib import Path

from app import settings
from app.settings import store

DEFAULT_JSON = Path(store.__file__).parent / store.DEFAULT_FILE


def test_defaults_come_from_json() -> None:
    raw = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    assert settings.defaults() == {"model": raw["model"], "effort": raw["effort"]}


def test_load_without_user_is_defaults() -> None:
    assert settings.load() == settings.defaults()


def test_save_and_load_per_user(account) -> None:
    user_id = account["user_id"]
    settings.save(user_id, {"model": "gpt-5.5", "effort": "high"})
    loaded = settings.load(user_id)
    assert loaded == {"model": "gpt-5.5", "effort": "high"}
    # 다른 사용자·기본값은 안 바뀜
    assert settings.load() == settings.defaults()


def test_unknown_user_falls_back_to_defaults() -> None:
    assert settings.load("no_such_user_zzzz") == settings.defaults()
