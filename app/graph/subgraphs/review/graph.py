"""검수 2계층. surface‖intent 병렬 검수 후 통과하면 끝내고 실패하면 재작성함.

empathy·reason이 각자 build()를 호출해 자기 노드로 넣음. 한 벌만 만듦.
"""

from __future__ import annotations

import json
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
    "보는 게 좋아",
    "잡자",
    "보내주면",
    "줄여줄게",
    "해줄게",
)


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


def _as_notes(value: object) -> list[str]:
    """모델이 지적을 문자열 하나로 줄 때가 있음. list()로 감싸면 글자 단위로 쪼개짐."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _as_score(value: object) -> int:
    """`"8점"`, `"8/10"`, `8.5` 가 다 옴. 못 읽으면 0 — 한 번 더 다듬으라는 뜻."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(10, int(value)))
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return max(0, min(10, int(digits[:2]))) if digits else 0


def _as_ok(value: object) -> bool:
    """`{"ok": "false"}` 를 bool() 로 넘기면 True 가 됨. 키가 없을 때만 통과로 봄."""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    return str(value).strip().lower() not in {"false", "no", "0", "아니오", "아니요"}


def _friend_tone_notes(draft: str) -> list[str]:
    """실사용에서 반복된 상담식 거리 표현만 재작성 사유로 고정함."""
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


def _progress_fallback(draft: str, last_message: str) -> str:
    """세 번의 재작성도 조언이면 모델 문장 중 안전한 첫 반응만 남김."""
    if not _is_progress_report(last_message):
        return draft
    sentences = re.findall(r".*?[.!?](?:\s|$)|.+$", draft.strip())
    for sentence in sentences:
        candidate = sentence.strip()
        if candidate and not _friend_tone_notes(candidate) and not _unsolicited_advice_notes(
            candidate, last_message
        ):
            return candidate
    return "응."


def _safe_sentence_fallback(draft: str, last_message: str) -> str:
    """국소 수정이 실패하면 문제가 없는 첫 문장만 남김."""
    sentences = re.findall(r".*?[.!?](?:\s|$)|.+$", draft.strip())
    for sentence in sentences:
        candidate = sentence.strip()
        if candidate and not _friend_tone_notes(candidate) and not _unsolicited_advice_notes(
            candidate, last_message
        ):
            return candidate
    return "응, 그렇구나."


def _last_human_text(state: State) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return str(message.content)
    return ""


def _drafts(state: State) -> list[Draft]:
    """drafts는 NotRequired지만 review에 들어올 때는 write가 이미 하나 채워 둠."""
    return state.get("drafts", [])


def build(llm: BaseChatModel):
    """검수 서브그래프를 컴파일해서 돌려줌."""
    config = _config()
    max_rounds = config.get("max_rounds", 3)
    pass_score = config.get("pass_score", 7)
    local_edit_fast_path = config.get("local_edit_fast_path", False)
    progress_review_bypass = config.get("progress_review_bypass", False)
    surface_checklist = config.get("surface_checklist", [])
    intent_checklist = config.get("intent_checklist", [])

    def can_bypass(state: State) -> bool:
        draft = _drafts(state)[-1]["text"]
        last_message = _last_human_text(state)
        arc = state.get("arc") or {}
        sentences = [item for item in re.findall(r".*?[.!?](?:\s|$)|.+$", draft.strip()) if item.strip()]
        return (
            progress_review_bypass
            and state.get("route") == "empathy"
            and arc.get("user_stance") == "보고"
            and _is_progress_report(last_message)
            and len(sentences) == 1
            and not _friend_tone_notes(draft)
            and not _unsolicited_advice_notes(draft, last_message)
            and "109" not in draft
            and "1577-0199" not in draft
        )

    async def surface(state: State) -> dict:
        draft = _drafts(state)[-1]["text"]
        if can_bypass(state):
            return {
                "surface_ok": True,
                "surface_notes": [],
                "surface_model_ok": True,
                "surface_model_notes": [],
                "surface_local_notes": [],
            }
        ai = await llm.ainvoke(prompt.surface_request(draft, state.get("persona"), surface_checklist))
        parsed = _parse(str(ai.content))
        model_notes = _as_notes(parsed.get("notes"))
        model_ok = _as_ok(parsed.get("ok"))
        local_notes = _friend_tone_notes(draft)
        return {
            "surface_ok": model_ok and not local_notes,
            "surface_notes": [*model_notes, *local_notes],
            "surface_model_ok": model_ok,
            "surface_model_notes": model_notes,
            "surface_local_notes": local_notes,
        }

    async def intent(state: State) -> dict:
        draft = _drafts(state)[-1]["text"]
        last_message = _last_human_text(state)
        if can_bypass(state):
            return {
                "intent_score": pass_score,
                "intent_notes": [],
                "intent_model_score": pass_score,
                "intent_model_notes": [],
                "intent_local_notes": [],
            }
        ai = await llm.ainvoke(
            prompt.intent_request(
                draft,
                state.get("route"),
                last_message,
                intent_checklist,
                arc=state.get("arc"),
            )
        )
        parsed = _parse(str(ai.content))
        model_notes = _as_notes(parsed.get("notes"))
        model_score = _as_score(parsed.get("score"))
        local_notes = _unsolicited_advice_notes(draft, last_message)
        return {
            "intent_score": 0 if local_notes else model_score,
            "intent_notes": [*model_notes, *local_notes],
            "intent_model_score": model_score,
            "intent_model_notes": model_notes,
            "intent_local_notes": local_notes,
        }

    def combine(state: State) -> dict:
        # surface·intent가 각자 다른 키에 쓰므로 여기서 한 초안 기록으로 합침
        notes = [*state.get("surface_notes", []), *state.get("intent_notes", [])]
        drafts = _drafts(state)
        scored: Draft = {
            "text": drafts[-1]["text"],
            "score": state.get("intent_score", 0),
            "ok": state.get("surface_ok", False),
            "notes": notes,
        }
        return {"drafts": [*drafts[:-1], scored]}

    def pick(state: State) -> str:
        passed = state.get("surface_ok", False) and state.get("intent_score", 0) >= pass_score
        local_notes = [
            *state.get("surface_local_notes", []),
            *state.get("intent_local_notes", []),
        ]
        only_local = (
            local_edit_fast_path
            and bool(local_notes)
            and state.get("surface_model_ok", False)
            and state.get("intent_model_score", 0) >= pass_score
            and not state.get("surface_model_notes", [])
            and not state.get("intent_model_notes", [])
            and "109" not in _drafts(state)[-1]["text"]
            and "1577-0199" not in _drafts(state)[-1]["text"]
        )
        notes = _drafts(state)[-1].get("notes", [])
        retry_limit = max_rounds + int(any("요청하지 않은 조언" in note for note in notes))
        if passed or len(_drafts(state)) >= retry_limit:
            return "finish"
        return "local_edit" if only_local else "rewrite"

    async def local_edit(state: State) -> dict:
        current = _drafts(state)[-1]
        last_message = _last_human_text(state)
        local_notes = [
            *state.get("surface_local_notes", []),
            *state.get("intent_local_notes", []),
        ]
        ai = await llm.ainvoke(prompt.rewrite_request(current["text"], local_notes, last_message))
        text = str(ai.content).strip()
        remaining = [*_friend_tone_notes(text), *_unsolicited_advice_notes(text, last_message)]
        if not text or remaining:
            text = _safe_sentence_fallback(text or current["text"], last_message)
        draft: Draft = {"text": text, "score": pass_score, "ok": True, "notes": []}
        return {"drafts": [*_drafts(state), draft]}

    async def rewrite(state: State) -> dict:
        current = _drafts(state)[-1]
        ai = await llm.ainvoke(
            prompt.rewrite_request(current["text"], current["notes"], _last_human_text(state))
        )
        draft: Draft = {"text": str(ai.content), "score": 0, "ok": False, "notes": []}
        return {"drafts": [*_drafts(state), draft]}

    def finish(state: State) -> dict:
        """표면 통과를 먼저 보고, 점수가 같으면 더 짧은 초안을 고름.

        재작성이 '지적만 고치고 나머지 유지'라 라운드마다 길이가 늘기만 하던 래칫을 끊음.
        """
        drafts = _drafts(state)
        last_message = _last_human_text(state)
        safe = [
            draft
            for draft in drafts
            if not _friend_tone_notes(draft["text"])
            and not _unsolicited_advice_notes(draft["text"], last_message)
        ]
        best = max(safe or drafts, key=lambda d: (d["ok"], d["score"], -len(d["text"])))
        text = (
            best["text"]
            if safe
            else _progress_fallback(drafts[-1]["text"], last_message)
        )
        return {
            "messages": [AIMessage(content=text)],
            "asked": False,
        }

    builder = StateGraph(State)
    builder.add_node("surface", surface)
    builder.add_node("intent", intent)
    builder.add_node("combine", combine)
    builder.add_node("local_edit", local_edit)
    builder.add_node("rewrite", rewrite)
    builder.add_node("finish", finish)
    builder.add_edge(START, "surface")
    builder.add_edge(START, "intent")
    builder.add_edge("surface", "combine")
    builder.add_edge("intent", "combine")
    builder.add_conditional_edges(
        "combine",
        pick,
        {"finish": "finish", "local_edit": "local_edit", "rewrite": "rewrite"},
    )
    builder.add_edge("local_edit", "finish")
    builder.add_edge("rewrite", "surface")
    builder.add_edge("rewrite", "intent")
    builder.add_edge("finish", END)
    return builder.compile()
