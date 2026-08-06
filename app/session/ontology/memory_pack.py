"""큐레이터 기억 팩의 저장 형식과 만료 판정."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 2


def create(
    candidates: list[dict],
    tone_lines: list[str],
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> dict:
    created = now or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_ids": list(dict.fromkeys(str(item["id"]) for item in candidates if item.get("id"))),
        "tone_lines": tone_lines,
        "generated_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=ttl_seconds)).isoformat(),
    }


def candidate_ids(memory: dict) -> list[str]:
    current = memory.get("candidate_ids")
    if isinstance(current, list):
        return list(dict.fromkeys(str(item) for item in current if str(item)))
    legacy = memory.get("candidates")
    if not isinstance(legacy, list):
        return []
    return list(
        dict.fromkeys(
            str(item.get("id"))
            for item in legacy
            if isinstance(item, dict) and item.get("id")
        )
    )


def is_fresh(memory: dict, *, now: datetime | None = None) -> bool:
    if memory.get("schema_version") != SCHEMA_VERSION:
        return True
    try:
        expires = datetime.fromisoformat(str(memory["expires_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > (now or datetime.now(timezone.utc))
