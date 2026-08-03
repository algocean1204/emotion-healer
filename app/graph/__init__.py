"""메인 그래프 조립. 라우터가 고른 서브그래프로 넘긴다."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.router import make_router, pick
from app.graph.state import State
from app.graph.subgraphs import empathy, solution
from app.llm.provider import get_chat_model

ROUTER_NODE = "route"


def build_graph(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """인자는 테스트가 가짜 모델을 넣기 위한 것. 실제 실행은 둘 다 생략한다."""
    llm = llm or get_chat_model()
    checkpointer = checkpointer or MemorySaver()

    builder = StateGraph(State)
    builder.add_node(ROUTER_NODE, make_router(llm))
    builder.add_node("empathy", empathy.build(llm))
    builder.add_node("solution", solution.build(llm))

    builder.add_edge(START, ROUTER_NODE)
    builder.add_conditional_edges(
        ROUTER_NODE, pick, {"empathy": "empathy", "solution": "solution"}
    )
    builder.add_edge("empathy", END)
    builder.add_edge("solution", END)
    return builder.compile(checkpointer=checkpointer)
