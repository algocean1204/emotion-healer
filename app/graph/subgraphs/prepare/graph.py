"""추가 질문과 현재 감정 이해를 한 번에 준비하는 1계층."""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app import crisis, guide
from app.graph.state import Ask, State
from app.graph.subgraphs.prepare import prompt
from app.graph.subgraphs.prepare.analysis import graph as analysis_graph
from app.graph.subgraphs.prepare.analysis import make_analyze, make_question
from app.types import Feeling

CONFIG_FILE = "healer_question.json"

_TARGET = {
    "situation": "situation",
    "emotion": "question",
    "identity": "identity",
    "skip": END,
}


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _has_crisis_signal(messages: list, keywords: list[str]) -> bool:
    """마지막 사용자 발화만 봄. 지난 턴 위기어로 이후 대화가 계속 막히면 안 됨."""
    last = next(
        (message for message in reversed(messages) if getattr(message, "type", "") == "human"),
        None,
    )
    if last is None:
        return False
    return crisis.has_signal(str(last.content), keywords)


def _parse(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _feeling(value: object) -> Feeling:
    found = value if isinstance(value, dict) else {}
    return {
        "emotion": str(found.get("emotion", "")),
        "intensity": str(found.get("intensity", "")),
        "trigger": str(found.get("trigger", "")),
        "hidden": str(found.get("hidden", "")),
    }


def build(llm: BaseChatModel):
    """prepare 서브그래프를 컴파일해서 돌려줌."""
    hints = _config()
    crisis_keywords = guide.load_shared(crisis.CRISIS_FILE).get("keywords", [])
    emotion_vocab = guide.load(analysis_graph.__file__, analysis_graph.CONFIG_FILE)
    analyze = make_analyze(llm)
    question = make_question(llm)
    identity_examples = list(hints.get("identity_tone_examples", []))

    async def understand(state: State) -> dict:
        # 연속으로는 못 묻음. 직전 턴이 질문으로 끝났으면 LLM 없이 바로 skip
        if state.get("asked") or _has_crisis_signal(state["messages"], crisis_keywords):
            return {"ask": "skip", "asked": False, **await analyze(state)}
        askable = list(state.get("askable_slots") or [])
        boundaries = list(state.get("identity_boundaries") or [])
        ai = await llm.ainvoke(
            prompt.understand_request(
                state["messages"],
                hints,
                emotion_vocab,
                askable=askable,
                boundaries=boundaries,
            )
        )
        parsed = _parse(str(ai.content))
        answer = str(parsed.get("ask", "skip")).strip().lower()
        ask: Ask = "skip"
        # identity 는 후보가 있을 때만 허용 — 프롬프트에 없어도 모델이 지어낼 수 있음
        if "identity" in answer and askable:
            ask = "identity"
        elif "situation" in answer:
            ask = "situation"
        elif "emotion" in answer:
            ask = "emotion"
        result = {"ask": ask, "feeling": _feeling(parsed.get("feeling"))}
        return {**result, "asked": False} if ask == "skip" else result

    async def situation(state: State) -> dict:
        ai = await llm.ainvoke(prompt.situation_request(state["messages"]))
        return {"messages": [AIMessage(content=str(ai.content))], "asked": True}

    async def identity(state: State) -> dict:
        askable = list(state.get("askable_slots") or [])
        boundaries = list(state.get("identity_boundaries") or [])
        ai = await llm.ainvoke(
            prompt.identity_request(state["messages"], askable, identity_examples, boundaries=boundaries)
        )
        return {"messages": [AIMessage(content=str(ai.content))], "asked": True}

    def pick(state: State) -> str:
        return _TARGET.get(state.get("ask", "skip"), END)

    builder = StateGraph(State)
    builder.add_node("understand", understand)
    builder.add_node("situation", situation)
    builder.add_node("identity", identity)
    builder.add_node("question", question)
    builder.add_edge(START, "understand")
    builder.add_conditional_edges(
        "understand",
        pick,
        {
            "situation": "situation",
            "identity": "identity",
            "question": "question",
            END: END,
        },
    )
    builder.add_edge("situation", END)
    builder.add_edge("identity", END)
    builder.add_edge("question", END)
    return builder.compile()
