"""공감 1계층. write가 초안을 쓰고 review(2계층)가 통과시킴."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app import guide
from app.graph.state import State
from app.graph.subgraphs.empathy import prompt
from app.graph.subgraphs.review import build as build_review
from app.types import Draft

CONFIG_FILE = "healer_empathy.json"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def build(llm: BaseChatModel):
    """공감 서브그래프를 컴파일해서 돌려줌."""
    config = _config()

    async def write(state: State) -> dict:
        arc = state.get("arc")
        # both+handoff 일 때만 짧은 공감 — 방법 문단이 이어짐
        short_form = state.get("route") == "both" and bool((arc or {}).get("handoff"))
        ai = await llm.ainvoke(
            prompt.draft_request(
                state["messages"], state.get("persona"), config, short_form, arc=arc
            )
        )
        draft: Draft = {"text": str(ai.content), "score": 0, "ok": False, "notes": []}
        return {"drafts": [draft]}

    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_node("review", build_review(llm))
    builder.add_edge(START, "write")
    builder.add_edge("write", "review")
    builder.add_edge("review", END)
    return builder.compile()
