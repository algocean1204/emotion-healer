"""main의 분기 판단 노드. empathy·reason·both 중 하나를 고름."""

from __future__ import annotations

import json
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import END

from app.graph.state import Route, State

ROUTER_PROMPT = """\
당신은 분류기입니다. 대화 상대가 아닙니다. 위로·조언·설명을 쓰지 마세요.

사용자의 마지막 메시지와 감정 분석 결과(있으면)를 보고 라벨 하나만 고르세요.

- empathy: 감정을 쏟내는 글, 조언을 요청하지 않은 글
- reason: 어떻게 할지·다음 단계를 묻는 글
- both: 감정도 크고 다음 단계도 궁금해하는 글

context 의 "원하는 것"이 방법이면 reason 쪽, 감정적 지지면 empathy 쪽을 기울이세요.
애매하면 empathy.

예시:
입력: 오늘 너무 울고 싶어요
출력: empathy
입력: 면접 준비 어떻게 할까요
출력: reason
입력: 힘들어서 이직할지 모르겠어요
출력: both

출력은 empathy 또는 reason 또는 both 한 단어뿐. 마침표·문장·다른 말 금지.
"""


def make_router(llm: BaseChatModel):
    """라우터 노드를 만듦."""

    async def route(state: State) -> dict:
        context = json.dumps(
            {
                "feeling": state.get("feeling"),
                "원하는 것": state.get("identity_wants") or [],
            },
            ensure_ascii=False,
        )
        ai = await llm.ainvoke(
            [SystemMessage(content=ROUTER_PROMPT), SystemMessage(content=context), *state["messages"]]
        )
        answer = str(ai.content).strip().lower()
        # 부분 문자열로 보면 "reason보다는 empathy"가 reason이 됨. 한 단어면 그대로 믿고,
        # 문장으로 답하면 먼저 나온 이름을 고름. 아무것도 없으면 안전한 쪽인 empathy
        picked: Route = "empathy"
        if answer in ("empathy", "reason", "both"):
            picked = cast(Route, answer)
        else:
            found = [(answer.find(name), name) for name in ("empathy", "reason", "both") if name in answer]
            if found:
                picked = cast(Route, min(found)[1])
        return {"route": picked}

    return route


def pick(state: State) -> str:
    """persona 뒤 시작 분기. both·empathy 는 공감 먼저, reason 만 바로 방법."""
    return "reason" if state.get("route") == "reason" else "empathy"


def after_empathy(state: State) -> str:
    """both 이면서 handoff 가 열렸을 때만 방법으로 잇음. 남용하면 한 턴 이중 작성임."""
    if state.get("route") != "both":
        return END
    arc = state.get("arc") or {}
    return "reason" if arc.get("handoff") else END
