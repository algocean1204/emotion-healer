"""공감 분석 2계층. analyze가 feeling을 채우고 question이 그걸로 되묻음."""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app import guide
from app.graph.state import State
from app.graph.subgraphs.prepare.analysis import prompt
from app.types import Feeling

CONFIG_FILE = "healer_emotion.json"


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


def make_analyze(llm: BaseChatModel):
    """감정 판정 노드. 되묻는 턴에만 돌면 route·persona가 읽는 값이 늘 이전 턴 것이 됨 —
    답변 턴에서도 같은 노드를 써야 해서 서브그래프 밖으로 분리."""
    vocab = _config()

    async def analyze(state: State) -> dict:
        ai = await llm.ainvoke(prompt.analyze_request(state["messages"], vocab))
        parsed = _parse(str(ai.content))
        feeling: Feeling = {
            "emotion": str(parsed.get("emotion", "")),
            "intensity": str(parsed.get("intensity", "")),
            "trigger": str(parsed.get("trigger", "")),
            "hidden": str(parsed.get("hidden", "")),
        }
        return {"feeling": feeling}

    return analyze


def make_question(llm: BaseChatModel):
    async def question(state: State) -> dict:
        ai = await llm.ainvoke(prompt.question_request(state.get("feeling")))
        return {"messages": [AIMessage(content=str(ai.content))], "asked": True}

    return question


def build(llm: BaseChatModel):
    """공감 분석 서브그래프를 컴파일해서 돌려줌."""
    analyze = make_analyze(llm)

    question = make_question(llm)

    builder = StateGraph(State)
    builder.add_node("analyze", analyze)
    builder.add_node("question", question)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "question")
    builder.add_edge("question", END)
    return builder.compile()
