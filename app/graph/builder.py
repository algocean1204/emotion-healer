"""main 그래프 조립. prepare 뒤 orient → persona → 공감/방법 분기."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.graph import persona
from app.graph.router import after_empathy, pick
from app.graph.state import State
from app.graph.subgraphs import empathy, orient, prepare, reason
from app.llm.provider import get_chat_model

ORIENT_NODE = "orient"
# 옛 이름 호환. progress 문구·테스트 마커가 route 를 쓰던 자리
ROUTER_NODE = ORIENT_NODE


def _after_prepare(state: State) -> str:
    return END if state.get("asked") else ORIENT_NODE


def build_graph(llm: BaseChatModel | None = None):
    """인자는 테스트가 가짜 모델을 넣기 위한 것. checkpointer는 없음 — 세션 JSON이 대신함."""
    if llm is None:
        llm = get_chat_model()

    builder = StateGraph(State)
    builder.add_node("prepare", prepare.build(llm))
    builder.add_node(ORIENT_NODE, orient.build(llm))
    builder.add_node("persona", persona.build(llm))
    builder.add_node("empathy", empathy.build(llm))
    builder.add_node("reason", reason.build(llm))

    builder.add_edge(START, "prepare")
    builder.add_conditional_edges("prepare", _after_prepare, {ORIENT_NODE: ORIENT_NODE, END: END})
    builder.add_edge(ORIENT_NODE, "persona")
    builder.add_conditional_edges("persona", pick, {"empathy": "empathy", "reason": "reason"})
    builder.add_conditional_edges("empathy", after_empathy, {"reason": "reason", END: END})
    builder.add_edge("reason", END)
    return builder.compile()
