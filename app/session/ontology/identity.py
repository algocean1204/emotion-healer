"""정체성 슬롯 조회·질문 가능 여부. LLM 없음."""

from __future__ import annotations

from app import guide
from app.session.ontology import graph_store
from app.session.ontology.schema import SLOT_VALUES

CONFIG_FILE = "healer_ontology.json"

SLOT_LABELS = {
    "name": "호칭",
    "day": "생활의 기반",
    "people": "곁의 사람",
    "want": "원하는 것",
    "boundary": "경계",
}


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def filled_slots(thread_id: str) -> dict[str, list[str]]:
    """슬롯 → 값 목록. origin=user · active 만."""
    found: dict[str, list[str]] = {}
    for row in graph_store.identity(thread_id):
        slot = row["slot"]
        found.setdefault(slot, []).append(row["value"])
    return found


def identity_lines(thread_id: str) -> list[str]:
    """게이트 맨 앞에 붙일 정체성 한 줄들."""
    lines = []
    for slot, values in filled_slots(thread_id).items():
        label = SLOT_LABELS.get(slot, slot)
        for value in values:
            lines.append(f"[정체성·{label}] {value}.")
    return lines


def askable_slots(
    thread_id: str,
    *,
    turn: int,
    identity_asks: int,
    turns_since_identity: int | None,
    crisis: bool,
    intensity: str | None,
) -> list[str]:
    """안전상 물으면 안 되는 때를 제외한 빈 슬롯. 자연스러움은 질문 에이전트가 판단함."""
    config = _config().get("identity", {})
    block = config.get("block_when", {})

    if crisis and block.get("crisis", True):
        return []
    if intensity and intensity in block.get("intensity", ["높음"]):
        return []

    filled = set(filled_slots(thread_id))
    # 이미 채운 슬롯은 능동 질문에서 뺌 — 같은 정보를 다시 캐묻지 않음
    return [slot for slot in SLOT_VALUES if slot not in filled]
