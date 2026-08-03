"""그래프 배선 스모크 테스트. 네트워크도 Codex도 안 탄다."""

from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_graph


class FakeModel:
    """라우터는 ainvoke, 서브그래프는 astream을 쓴다. 둘 다 흉내낸다."""

    def __init__(self, route: str = "empathy") -> None:
        self.route = route
        self.seen: list[Any] = []

    async def ainvoke(self, messages, **_kwargs) -> AIMessage:
        self.seen.append(messages)
        return AIMessage(content=self.route)

    async def astream(self, messages, **_kwargs) -> AsyncIterator[AIMessageChunk]:
        self.seen.append(messages)
        for part in ("들으니 ", "많이 힘드셨겠어요."):
            yield AIMessageChunk(content=part)


async def test_routes_to_empathy() -> None:
    model = FakeModel(route="empathy")
    graph = build_graph(llm=model, checkpointer=MemorySaver())

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="오늘 회의에서 의견이 묻혔어")]},
        {"configurable": {"thread_id": "t1"}},
    )

    assert out["route"] == "empathy"
    assert out["messages"][-1].content == "들으니 많이 힘드셨겠어요."
    # 라우터가 먼저 돌고 공감 서브그래프가 이어받는다
    assert "empathy" in model.seen[0][0].content
    assert "공감이 필요한 상황" in model.seen[1][0].content


async def test_routes_to_solution() -> None:
    model = FakeModel(route="solution")
    graph = build_graph(llm=model, checkpointer=MemorySaver())

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="이직 제안을 받았는데 어떻게 할까")]},
        {"configurable": {"thread_id": "t2"}},
    )

    assert out["route"] == "solution"
    assert "방법이 필요한 상황" in model.seen[1][0].content


async def test_keeps_history_per_thread() -> None:
    model = FakeModel()
    graph = build_graph(llm=model, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t3"}}

    await graph.ainvoke({"messages": [HumanMessage(content="첫 얘기")]}, config)
    out = await graph.ainvoke({"messages": [HumanMessage(content="이어서")]}, config)

    # user + ai + user + ai
    assert len(out["messages"]) == 4
