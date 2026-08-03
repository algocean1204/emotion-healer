"""해결 서브그래프. 감정을 받은 뒤 실제로 해볼 것을 꺼낸다."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graph.state import State
from app.prompt import BASE_PROMPT

SOLUTION_PROMPT = (
    BASE_PROMPT
    + """
## 지금은 방법이 필요한 상황입니다

그래도 감정을 먼저 받고, 그 다음에 방법을 꺼내세요. 순서를 바꾸면 조언이
훈계로 들립니다.

막연한 위로 대신 오늘 당장 해볼 수 있는 것을 말하세요. 한두 개면 충분합니다.
"""
)


def build(llm: BaseChatModel):
    """해결 서브그래프를 컴파일해서 돌려준다."""

    async def respond(state: State) -> dict:
        parts: list[str] = []
        async for chunk in llm.astream(
            [SystemMessage(content=SOLUTION_PROMPT), *state["messages"]]
        ):
            parts.append(str(chunk.content))
        return {"messages": [AIMessage(content="".join(parts))]}

    builder = StateGraph(State)
    builder.add_node("respond", respond)
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
