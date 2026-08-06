"""압축 그래프. START → gate ─┬─ END / └─ score → shrink → verify → END."""

from __future__ import annotations

import json
from typing import NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app import guide
from app.session.compress import prompt, rules
from app.session.store import Session

CONFIG_FILE = "healer_compress.json"
CRISIS_FILE = "healer_crisis.json"


class CompressState(TypedDict):
    """session·thread_id만 입력으로 받고 나머지는 노드가 채움."""

    session: Session
    thread_id: str
    should_compress: NotRequired[bool]
    sentences: NotRequired[list[dict]]
    graded: NotRequired[list[dict]]
    summaries: NotRequired[list[dict]]
    bridges: NotRequired[list[dict]]
    result: NotRequired[Session]


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _parse_json(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build(llm: BaseChatModel, budget_chars: int = 0):
    """압축 그래프를 컴파일해서 돌려줌. budget_chars가 0이면 json 임계로 떨어짐."""
    config = _config()
    threshold_chars = budget_chars or config.get("threshold_chars", 0)
    recent_turns = config.get("recent_turns", 0)
    keep_ratio_max = config.get("keep_ratio_max", 1.0)
    crisis_keywords = guide.load_shared(CRISIS_FILE).get("keywords", [])

    def gate(state: CompressState) -> dict:
        session = state["session"]
        total_chars = sum(
            len(str(message.get("data", {}).get("content", "")))
            for message in session["messages"]
        )
        return {"should_compress": total_chars >= threshold_chars, "result": session}

    def pick(state: CompressState) -> str:
        return "score" if state.get("should_compress") else END

    async def score(state: CompressState) -> dict:
        sentences = rules.to_sentences(state["session"])
        candidates = rules.scoring_candidates(sentences, recent_turns)

        graded: list[dict] = []
        if candidates:
            ai = await llm.ainvoke(prompt.score_request(candidates))
            graded = _parse_json(str(ai.content)).get("sentences", []) or []
        graded += rules.fixed_keep_grades(sentences, recent_turns)

        graded = rules.fill_missing(sentences, graded)
        graded = rules.enforce_crisis(sentences, graded, crisis_keywords)
        protected = rules.crisis_ids(sentences, crisis_keywords) | rules.recent_ids(sentences, recent_turns)
        graded = rules.cap_keep_ratio(graded, keep_ratio_max, protected)
        graded = rules.enforce_turn_pairs(sentences, graded)
        return {"sentences": sentences, "graded": graded}

    async def shrink(state: CompressState) -> dict:
        graded = state.get("graded", [])
        if not any(record["grade"] in {"summarize", "drop"} for record in graded):
            return {"summaries": [], "bridges": []}
        ai = await llm.ainvoke(prompt.shrink_request(state.get("sentences", []), graded))
        parsed = _parse_json(str(ai.content))
        return {"summaries": parsed.get("summaries", []) or [], "bridges": parsed.get("bridges", []) or []}

    def verify(state: CompressState) -> dict:
        sentences, graded = state.get("sentences", []), state.get("graded", [])
        if not rules.covers_all(sentences, graded):
            return {}
        if not rules.grades_valid(graded):
            return {}
        if not rules.crisis_kept(sentences, graded, crisis_keywords):
            return {}
        # ontology·memory는 세션에 이미 실려 있어 apply_grades가 그대로 넘겨줌
        return {
            "result": rules.apply_grades(
                state["session"], sentences, graded, state.get("summaries", []), state.get("bridges", [])
            )
        }

    builder = StateGraph(CompressState)
    builder.add_node("gate", gate)
    builder.add_node("score", score)
    builder.add_node("shrink", shrink)
    builder.add_node("verify", verify)
    builder.add_edge(START, "gate")
    builder.add_conditional_edges("gate", pick, {"score": "score", END: END})
    builder.add_edge("score", "shrink")
    builder.add_edge("shrink", "verify")
    builder.add_edge("verify", END)
    return builder.compile()


async def run(
    session: Session, llm: BaseChatModel, thread_id: str, budget_chars: int = 0
) -> Session:
    """세션 하나를 압축 그래프에 태워 결과 세션을 받음."""
    out = await build(llm, budget_chars).ainvoke({"session": session, "thread_id": thread_id})
    return out["result"]
