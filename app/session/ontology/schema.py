"""OntologyNode 검증과 기본값 채우기. 판정은 여기서 하지 않음."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

KIND_VALUES = ("observation", "interpretation", "intent")
SPAN_VALUES = ("state", "event")
ORIGIN_VALUES = ("user", "inferred")
STATUS_VALUES = ("active", "superseded", "retracted")
# enum 밖이면 None — kind 와 같은 패턴. 모르는 슬롯을 저장하면 조회·질문이 어긋남
SLOT_VALUES = ("name", "day", "people", "want", "boundary")

# 읽기 시 결손 키를 메움. Neo4j 옛 노드에 필드가 없어도 호출부가 KeyError 로 안 죽음
NODE_DEFAULTS: dict = {
    "source_message_ids": [],
    "kind": "interpretation",
    "span": "state",
    "origin": "user",
    "occurred_at": None,
    "valid_from": None,
    "valid_to": None,
    "tags": [],
    "alias_of": None,
    "status": "active",
    "superseded_by": None,
    "disclosure": "quiet",
    "crisis": False,
    "sensitivity": False,
    "extraction_confidence": 0.5,
    "salience": 0.5,
    "slot": None,
}


def _clamp01(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def build(raw: dict, thread_id: str, source_message_ids: list[str]) -> dict | None:
    """LLM 추출 결과 하나를 OntologyNode로 채움. subject·predicate·object가 없으면 버림."""
    subject = str(raw.get("subject", "")).strip()
    predicate = str(raw.get("predicate", "")).strip()
    obj = str(raw.get("object", "")).strip()
    if not subject or not predicate or not obj:
        return None

    kind = raw.get("kind")
    if kind not in KIND_VALUES:
        kind = "interpretation"  # 애매하면 해석으로 떨어뜨림

    span = raw.get("span") if raw.get("span") in SPAN_VALUES else "state"
    origin = raw.get("origin") if raw.get("origin") in ORIGIN_VALUES else "user"
    slot = raw.get("slot") if raw.get("slot") in SLOT_VALUES else None

    return {
        "id": uuid.uuid4().hex,
        "thread_id": thread_id,
        "source_message_ids": source_message_ids,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "kind": kind,
        "span": span,
        "origin": origin,
        "occurred_at": raw.get("occurred_at"),
        "valid_from": datetime.now(timezone.utc).isoformat(),
        "valid_to": None,
        "tags": [str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip()],
        "alias_of": None,
        "status": "active",
        "superseded_by": None,
        "disclosure": "quiet",  # 승격은 store.classify_disclosure가 판정함
        "crisis": bool(raw.get("crisis", False)),
        "sensitivity": bool(raw.get("sensitivity", False)),
        "extraction_confidence": _clamp01(raw.get("extraction_confidence", 0.5)),
        "salience": _clamp01(raw.get("salience", 0.5)),
        "slot": slot,
    }