"""LangGraph 그래프. 지금은 노드 하나."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from app.llm.provider import get_chat_model
from app.prompt import SYSTEM_PROMPT


def build_graph(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """인자는 테스트가 가짜 모델을 넣기 위한 것. 실제 실행은 둘 다 생략한다."""
    llm = llm or get_chat_model()
    checkpointer = checkpointer or MemorySaver()

    async def respond(state: MessagesState) -> dict:
        parts: list[str] = []
        async for chunk in llm.astream(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        ):
            parts.append(str(chunk.content))
        return {"messages": [AIMessage(content="".join(parts))]}

    builder = StateGraph(MessagesState)
    builder.add_node("respond", respond)
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)
