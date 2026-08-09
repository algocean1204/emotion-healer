"""초안을 한 번 검수하고 필요한 부분만 고치는 프롬프트."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

from app.prompt import crisis_prompt
from app.types import Arc, Persona, Route

FINALIZE_PROMPT = """\
아래 초안을 실제 친구가 보낼 최종 답으로 한 번만 다듬으세요.
문제가 없으면 초안을 한 글자도 바꾸지 마세요. 문제가 있을 때도 새로 쓰지 말고 그 부분만 고치세요.

- 사용자의 마지막 말에 실제로 답하세요.
- 현재 대화 방향과 금지 사항을 지키세요.
- 길이를 늘리지 마세요.
- 상담식 거리 표현과 요청하지 않은 조언을 빼세요.
- 사용자가 한 일을 보고했을 뿐이면 칭찬·평가·다음 행동을 보태지 말고 그 사실에만 반응하세요.
- 못 찾은 기억은 `언제 말했는지 기억나? 아니면 다시 들려줘.`처럼 묻고 `어느 때쯤`, `언제쯤`은 쓰지 마세요.
- 초안의 위기 상담 번호는 절대 빼지 마세요.
- 검수 설명, 점수, JSON 없이 최종 답만 출력하세요.

## 확인할 항목
{checklist}
"""


def finalize_request(
    draft: str,
    persona: Persona | None,
    route: Route | None,
    last_message: str,
    surface_checklist: list[str],
    intent_checklist: list[str],
    arc: Arc | None = None,
) -> list[BaseMessage]:
    forbidden = (persona or {}).get("forbidden", [])
    items = [
        *surface_checklist,
        *intent_checklist,
        *(f"금지 위반: {item}" for item in forbidden),
    ]
    payload = {
        "draft": draft,
        "last_message": last_message,
        "route": route or "empathy",
        "arc": arc or {},
    }
    return [
        SystemMessage(
            content=FINALIZE_PROMPT.format(
                checklist="\n".join(f"- {item}" for item in items)
            ) + "\n" + crisis_prompt()
        ),
        SystemMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
