"""그래프가 주고받는 상태."""

from __future__ import annotations

from typing import NotRequired

from langgraph.graph import MessagesState

from app.types import Arc, Ask, Draft, Feeling, Persona, Route

__all__ = ["Arc", "Ask", "Draft", "Feeling", "Persona", "Route", "State"]


class State(MessagesState):
    """messages는 MessagesState가 줌. 나머지는 노드가 채우므로 입력에 없어도 됨."""

    ask: NotRequired[Ask]
    asked: NotRequired[bool]
    feeling: NotRequired[Feeling | None]
    persona: NotRequired[Persona | None]
    route: NotRequired[Route]
    drafts: NotRequired[list[Draft]]
    # main 이 채운 정체성 문맥. prepare decide·router 가 읽음
    askable_slots: NotRequired[list[str]]
    identity_wants: NotRequired[list[str]]
    identity_boundaries: NotRequired[list[str]]
    # 직전 턴 arc(세션) + 이번 턴 orient 결과
    previous_arc: NotRequired[Arc | None]
    arc: NotRequired[Arc | None]

    # review 2계층 전용. surface·intent 가 병렬로 채우고 combine 이 합침
    surface_ok: NotRequired[bool]
    surface_notes: NotRequired[list[str]]
    surface_model_ok: NotRequired[bool]
    surface_model_notes: NotRequired[list[str]]
    surface_local_notes: NotRequired[list[str]]
    intent_score: NotRequired[int]
    intent_notes: NotRequired[list[str]]
    intent_model_score: NotRequired[int]
    intent_model_notes: NotRequired[list[str]]
    intent_local_notes: NotRequired[list[str]]
