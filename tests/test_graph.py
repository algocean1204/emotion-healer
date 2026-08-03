"""그래프 배선 스모크 테스트. 네트워크도 Codex도 안 탄다."""

from typing import Any, AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_graph


class FakeModel:
    """노드를 돌리는 데 필요한 만큼만 흉내낸 모델."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    async def astream(self, messages, **_kwargs) -> AsyncIterator[AIMessageChunk]:
        self.seen.append(messages)
        for part in ("들으니 ", "많이 힘드셨겠어요."):
            yield AIMessageChunk(content=part)


async def test_node_streams_and_keeps_history() -> None:
    model = FakeModel()
    graph = build_graph(llm=model, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="오늘 회의에서 의견이 묻혔어")]}, config
    )
    assert first["messages"][-1].content == "들으니 많이 힘드셨겠어요."

    # 시스템 프롬프트가 앞에 붙고 사용자 turn이 모델까지 간다
    assert "위기 신호" in model.seen[0][0].content
    assert model.seen[0][-1].content == "오늘 회의에서 의견이 묻혔어"

    # 같은 thread_id면 앞선 대화가 이어진다
    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="그리고 또 있어")]}, config
    )
    assert len(second["messages"]) == 4
    assert len(model.seen[1]) == 4  # system + user + ai + user
