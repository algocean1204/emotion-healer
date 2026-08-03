"""메인 그래프의 분기 판단. 공감이 필요한지 방법이 필요한지 고른다."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage

from app.graph.state import Route, State

ROUTER_PROMPT = """\
사용자의 마지막 메시지를 보고 지금 필요한 것을 고르세요.

- empathy: 감정을 쏟아내는 글, 조언을 요청하지 않은 글, 답을 알면서 힘들다는 글
- solution: 구체적인 상황을 놓고 어떻게 할지 묻는 글, 다음 단계를 찾는 글

애매하면 empathy를 고르세요.
둘 중 한 단어만 답하세요. 다른 말은 붙이지 마세요.
"""


def make_router(llm: BaseChatModel):
    """라우터 노드를 만든다."""

    async def route(state: State) -> dict:
        ai = await llm.ainvoke(
            [SystemMessage(content=ROUTER_PROMPT), *state["messages"]]
        )
        answer = str(ai.content).strip().lower()
        return {"route": "solution" if "solution" in answer else "empathy"}

    return route


def pick(state: State) -> Route:
    """조건부 엣지가 읽는 분기 값."""
    return state["route"]
