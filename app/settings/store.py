"""사용자 설정. 기본값은 파일, 사용자 값은 Postgres.

제품 공통 정책(healer_review.json 등)은 파일 그대로 둠.
모델·effort 처럼 사람마다 다른 것만 DB 에 둠.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from app import guide
from app.auth import store as auth_store

log = logging.getLogger(__name__)
DEFAULT_FILE = "healer_default.json"


class Settings(TypedDict):
    model: str
    effort: str


def defaults() -> Settings:
    """기본값은 코드 상수가 아니라 healer_default.json 에서 옴."""
    raw = guide.load(__file__, DEFAULT_FILE)
    return {"model": str(raw.get("model", "")), "effort": str(raw.get("effort", ""))}


def _merge(base: Settings, patch: dict | None) -> Settings:
    if not isinstance(patch, dict):
        return base
    return {
        "model": str(patch.get("model") or base["model"]),
        "effort": str(patch.get("effort") or base["effort"]),
    }


def load(user_id: str | None = None) -> Settings:
    """user_id 가 있으면 그 사람 설정을 읽고, 없거나 실패하면 파일 기본값."""
    base = defaults()
    if not user_id:
        return base
    try:
        with auth_store.connect() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM user_preferences WHERE user_id = %s",
                (user_id,),
            )
            row = cursor.fetchone()
    except Exception:
        log.exception("설정 읽기 실패 user=%s — 기본값 사용", user_id)
        return base
    if not row:
        return base
    payload = row[0]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return base
    return _merge(base, payload if isinstance(payload, dict) else None)


def save(user_id: str, settings: Settings) -> Settings:
    """사용자 설정을 upsert. 기본값 파일은 건드리지 않음."""
    cleaned: Settings = {
        "model": str(settings["model"]),
        "effort": str(settings["effort"]),
    }
    payload = json.dumps(cleaned, ensure_ascii=False)
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_preferences (user_id, payload, updated_at)
            VALUES (%s, %s::jsonb, now())
            ON CONFLICT (user_id) DO UPDATE
              SET payload = EXCLUDED.payload,
                  updated_at = now()
            """,
            (user_id, payload),
        )
        db.commit()
    return cleaned
