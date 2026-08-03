"""공감 서브그래프. 해결책 대신 감정을 받는다."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graph.state import State
from app.prompt import BASE_PROMPT

EMPATHY_PROMPT = (
    BASE_PROMPT
    + """
## 지금은 공감이 필요한 상황입니다

해결책을 꺼내지 마세요. 같이 있어주는 게 답입니다.

"이렇게 해보세요", "그래도 좋은 점은" 같은 말은 지금 상대를 더 외롭게 만듭니다.
힘든 게 당연하다는 것만 분명히 전하세요.
"""
)


def build(llm: BaseChatModel):
    """공감 서브그래프를 컴파일해서 돌려준다."""

    async def respond(state: State) -> dict:
        parts: list[str] = []
        async for chunk in llm.astream(
            [SystemMessage(content=EMPATHY_PROMPT), *state["messages"]]
        ):
            parts.append(str(chunk.content))
        return {"messages": [AIMessage(content="".join(parts))]}

    builder = StateGraph(State)
    builder.add_node("respond", respond)
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
