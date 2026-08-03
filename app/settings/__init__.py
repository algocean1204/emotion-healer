"""healer-setting.json 읽고 쓰기."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

PATH = Path(__file__).resolve().parents[2] / "healer-setting.json"

DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "max"


class Settings(TypedDict):
    model: str
    effort: str


def defaults() -> Settings:
    return {"model": DEFAULT_MODEL, "effort": DEFAULT_EFFORT}


def load() -> Settings:
    """파일이 없거나 깨져 있어도 기본값으로 뜬다. 설정 때문에 앱이 죽지 않게."""
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults()
    if not isinstance(raw, dict):
        return defaults()
    return {
        "model": str(raw.get("model") or DEFAULT_MODEL),
        "effort": str(raw.get("effort") or DEFAULT_EFFORT),
    }


def save(settings: Settings) -> Settings:
    PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return settings
