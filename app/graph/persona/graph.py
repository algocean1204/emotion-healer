"""페르소나 생성 노드. main의 노드이며 route와 병렬 실행."""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel

from app import guide
from app.graph.persona import prompt
from app.graph.state import State
from app.types import Persona, Route

CONFIG_FILE = "healer_persona.json"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _parse(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_items(value: object) -> list[str]:
    """모델이 항목 하나를 문자열로 줄 때가 있음. list()로 감싸면 글자 단위로 쪼개짐."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _drop_conflicts(forbidden: list[str], route: Route | None, conflicts: dict) -> list[str]:
    """분기가 할 일을 금지어로 들고 나오면 그 초안은 정의상 검수를 통과 못 함.
    프롬프트로도 막지만 한 번 새면 그 턴 LLM 6회가 통째로 낭비라 코드에서 한 번 더 차단."""
    words = conflicts.get(route or "empathy", [])
    return [item for item in forbidden if not any(word in item for word in words)]


def _last_human_text(state: State) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return str(message.content)
    return ""


def build(llm: BaseChatModel):
    """페르소나 노드를 만듦. 금지·길이만 여기서 강제하고 축은 예시로만 줌."""
    config = _config()
    refresh_every_turns = int(config.get("refresh_every_turns", 4))
    max_tone_items = config.get("max_tone_items", 3)
    max_forbidden_items = config.get("max_forbidden_items", 4)
    max_view_chars = config.get("max_view_chars", 60)
    tone_axes = config.get("example_tone_axes", [])
    route_conflicts = config.get("route_conflicts", {})

    async def persona_node(state: State) -> dict:
        route = state.get("route")
        arc = state.get("arc")
        boundaries = list(state.get("identity_boundaries") or [])
        previous = state.get("persona")
        # orient 가 정한 do_not 은 코드로 강제 합침
        arc_do_not = list((arc or {}).get("do_not") or [])
        turn = int(state.get("turn") or 0)
        persona_turn = state.get("persona_turn")
        previous_arc = state.get("previous_arc") or {}
        previous_forbidden = previous.get("forbidden", []) if previous else []
        refresh = (
            previous is None
            or persona_turn is None
            or turn - int(persona_turn) >= refresh_every_turns
            or previous_arc.get("mode") != (arc or {}).get("mode")
            or (arc or {}).get("phase") == "위기"
            or (arc or {}).get("user_stance") in {"조언거절", "반박"}
            or any(boundary not in previous_forbidden for boundary in boundaries)
        )
        if not refresh:
            assert previous is not None
            forbidden = []
            for item in [*boundaries, *arc_do_not, *previous_forbidden]:
                if item and item not in forbidden:
                    forbidden.append(item)
            return {
                "persona": {
                    "tone": previous.get("tone", [])[:max_tone_items],
                    "view": str((arc or {}).get("next_move") or previous.get("view", ""))[:max_view_chars],
                    "forbidden": _drop_conflicts(forbidden, route, route_conflicts)[:max_forbidden_items],
                },
                "persona_turn": persona_turn,
            }
        ai = await llm.ainvoke(
            prompt.request(
                state.get("feeling"),
                _last_human_text(state),
                previous,
                tone_axes,
                route,
                boundaries=boundaries,
                arc=arc,
            )
        )
        parsed = _parse(str(ai.content))
        merged: list[str] = []
        for item in [
            *boundaries,
            *arc_do_not,
            *(previous.get("forbidden", []) if previous else []),
            *_as_items(parsed.get("forbidden")),
        ]:
            if item and item not in merged:
                merged.append(item)
        result: Persona = {
            "tone": _as_items(parsed.get("tone"))[:max_tone_items],
            "view": str(parsed.get("view", ""))[:max_view_chars],
            "forbidden": _drop_conflicts(merged, route, route_conflicts)[:max_forbidden_items],
        }
        return {"persona": result, "persona_turn": turn}

    return persona_node
