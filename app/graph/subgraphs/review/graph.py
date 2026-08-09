"""초안을 한 번 검수하고 필요한 부분만 고치는 최종 다듬기."""

from __future__ import annotations

import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app import guide
from app.graph.state import State
from app.graph.subgraphs.review import prompt
from app.types import Draft

CONFIG_FILE = "healer_review.json"

_DISTANCED_FRIEND_PATTERNS = (
    "몸도 마음도",
    "불안하고 막막",
    "그 느낌",
    "그 상태",
    "할 수 있겠다",
    "될 수 있겠다",
    "안도되",
    "뿌듯하겠",
)

_PROGRESS_MARKERS = (
    "중이야",
    "하는 중",
    "하고 있어",
    "했어",
    "찾았어",
    "봤어",
    "뒀어",
    "끝났어",
    "끝냈어",
    "보냈어",
    "됐어",
    "해놨어",
)
_REQUEST_MARKERS = ("?", "어떻게", "뭐부터", "뭘 해야", "도와", "조언", "방법")
_ADVICE_MARKERS = (
    "해봐",
    "찾아봐",
    "훑어봐",
    "하면 돼",
    "해야 해",
    "먼저 보",
    "부터 보",
    "만 잡",
    "잘하고 있어",
    "잘했어",
    "찾아보자",
    "기다려",
    "해보자",
    "보는 게 좋아",
    "잡자",
    "보내주면",
    "줄여줄게",
    "해줄게",
)


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _friend_tone_notes(draft: str) -> list[str]:
    """실사용에서 반복된 상담식 거리 표현만 코드 안전선으로 잡음."""
    found = [pattern for pattern in _DISTANCED_FRIEND_PATTERNS if pattern in draft]
    if not found:
        return []
    return [f"친구의 생활어로 바꾸기: {', '.join(found)}"]


def _unsolicited_advice_notes(draft: str, last_message: str) -> list[str]:
    """진행 보고를 방법 요청으로 바꿔 읽은 초안만 잡음."""
    advice = [marker for marker in _ADVICE_MARKERS if marker in draft]
    if not _is_progress_report(last_message) or not advice:
        return []
    return [f"요청하지 않은 조언 빼기: {', '.join(advice)}"]


def _is_progress_report(last_message: str) -> bool:
    return any(marker in last_message for marker in _PROGRESS_MARKERS) and not any(
        marker in last_message for marker in _REQUEST_MARKERS
    )


def _safe_sentence_fallback(draft: str, last_message: str) -> str:
    """국소 수정이 실패하면 문제가 없는 첫 문장만 남김."""
    sentences = re.findall(r".*?[.!?](?:\s|$)|.+$", draft.strip())
    for sentence in sentences:
        candidate = sentence.strip()
        if candidate and not _friend_tone_notes(candidate) and not _unsolicited_advice_notes(
            candidate, last_message
        ):
            return candidate
    return "아, 그건 좀 그렇네."


def _last_human_text(state: State) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return str(message.content)
    return ""


def _drafts(state: State) -> list[Draft]:
    """drafts는 NotRequired지만 review에 들어올 때는 write가 이미 하나 채워 둠."""
    return state.get("drafts", [])


def _without_role_disclaimer(text: str) -> str:
    return re.sub(r"(?:나는|난)?\s*상담사는 아니지만,?\s*", "", text)


def _final_text(draft: str, candidate: str, last_message: str) -> str:
    draft = _without_role_disclaimer(draft.strip())
    text = _without_role_disclaimer(candidate.strip()) or draft
    required = [number for number in ("109", "1577-0199") if number in draft]
    if required:
        return draft.strip()
    for phrase in ("어느 때쯤", "어느때쯤", "언제쯤"):
        text = text.replace(phrase, "언제")
    if _friend_tone_notes(text) or _unsolicited_advice_notes(text, last_message):
        if not _friend_tone_notes(draft) and not _unsolicited_advice_notes(draft, last_message):
            text = draft.strip()
        else:
            text = _safe_sentence_fallback(text or draft, last_message)
    return text or "응."


def build(llm: BaseChatModel):
    """초안을 한 번 검수하고 필요한 부분만 고치는 최종 다듬기."""
    config = _config()
    surface_checklist = config.get("surface_checklist", [])
    intent_checklist = config.get("intent_checklist", [])

    async def finalize(state: State) -> dict:
        draft = _drafts(state)[-1]["text"]
        last_message = _last_human_text(state)
        ai = await llm.ainvoke(
            prompt.finalize_request(
                draft,
                state.get("persona"),
                state.get("route"),
                last_message,
                surface_checklist,
                intent_checklist,
                arc=state.get("arc"),
            )
        )
        return {
            "messages": [AIMessage(content=_final_text(draft, str(ai.content), last_message))],
            "asked": False,
        }

    builder = StateGraph(State)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()
