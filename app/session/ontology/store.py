"""온톨로지 판정 로직. 저장은 graph_store.py가 맡고 여기는 순수 함수만 둠."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.types import OntologyDisclosure


def normalize(node: dict, aliases: dict[str, str]) -> dict:
    """subject·tags를 사전 기준으로 정규화함. 사전에 없으면 그대로 두고 alias_of는 비움."""
    raw_subject = node["subject"]
    canonical = aliases.get(raw_subject, raw_subject)
    return {
        **node,
        "subject": canonical,
        "alias_of": raw_subject if canonical != raw_subject else None,
        "tags": list(dict.fromkeys(aliases.get(tag, tag) for tag in node["tags"])),
    }


def matches_any(text: str, patterns: list[str]) -> bool:
    """공개 헬퍼. remember 가 stop 신호를 같은 규칙으로 봄."""
    return any(re.search(pattern, text) for pattern in patterns)


def _matches_any(text: str, patterns: list[str]) -> bool:
    return matches_any(text, patterns)


def classify_disclosure(source_text: str, origin: str, config: dict) -> OntologyDisclosure:
    """새 노드가 만들어질 때 한 번만 판정함. 이미 있는 proactive 노드를 내리려면 quiet()를 씀."""
    signals = config.get("disclosure_signals", {})
    if origin == "inferred" or _matches_any(source_text, signals.get("stop", [])):
        return "quiet"  # 추론이거나 그만 말하라는 신호는 승격 신호보다 우선함
    if _matches_any(source_text, signals.get("remember", [])) or _matches_any(source_text, signals.get("dated", [])):
        return "proactive"
    return "quiet"


def decayed_salience(node: dict, config: dict, now: datetime | None = None) -> float:
    """오래된 노드일수록 salience를 깎음. valid_from이 없으면 원래 값 그대로."""
    salience = node.get("salience", 0.0)
    valid_from = node.get("valid_from")
    if not valid_from:
        return salience
    try:
        created = datetime.fromisoformat(valid_from)
    except ValueError:
        return salience
    days = max(((now or datetime.now(timezone.utc)) - created).total_seconds() / 86400, 0.0)
    decay_per_day = config.get("salience_decay_per_day", 0.0)
    return salience * max(1 - decay_per_day * days, 0.0)
