"""검수 프롬프트. 1차는 표면, 2차는 의도, 재작성은 지적을 모아 한 번에 고침."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

from app.prompt import crisis_prompt
from app.types import Arc, Persona, Route

SURFACE_PROMPT = """\
아래 초안을 검수합니다. 다음만 확인하세요.
{checklist}

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{{"ok": true, "notes": ["..."]}}
"""

INTENT_PROMPT = """\
아래 초안이 사용자가 물은 것에 답했는지, 지금 분기({route})의 결에 맞는지 봅니다.
{checklist}

대화 궤적이 있으면 그것도 보세요 — 같은 제안 재탕, 거절한 조언 재등장, 악화인데 성급한 해결을 내미는지.
0~10점으로 채점하세요. 평범한 좋은 답은 7~9, 부족한 답만 6 이하.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{{"score": 8, "notes": ["..."]}}
"""

REWRITE_PROMPT = """\
아래 초안을 지적을 반영해 다시 씁니다. 지적된 것만 고치세요.

- 길이를 늘리지 마세요. 가능하면 같은 길이이거나 더 짧게.
- 초안에 상담 창구 안내가 들어 있으면 절대 빼지 마세요.
- 같은 문장을 덧붙이며 부풀리지 마세요.

## 지적
{notes}
"""


def surface_request(draft: str, persona: Persona | None, checklist: list[str]) -> list[BaseMessage]:
    """1차(표면) 검수 요청. persona의 forbidden 위반도 같이 봄."""
    forbidden = (persona or {}).get("forbidden", [])
    items = [*checklist, *(f"금지 위반: {item}" for item in forbidden)]
    bullets = "\n".join(f"- {item}" for item in items)
    return [SystemMessage(content=SURFACE_PROMPT.format(checklist=bullets)), SystemMessage(content=draft)]


def intent_request(
    draft: str,
    route: Route | None,
    last_message: str,
    checklist: list[str],
    arc: Arc | None = None,
) -> list[BaseMessage]:
    """2차(의도) 검수 요청. 마지막 사용자 말과 궤적을 같이 줌."""
    bullets = "\n".join(f"- {item}" for item in checklist)
    payload = {
        "draft": draft,
        "last_message": last_message,
        "arc": (
            {
                "trajectory": (arc or {}).get("trajectory"),
                "commitments": (arc or {}).get("commitments"),
                "do_not": (arc or {}).get("do_not"),
                "next_move": (arc or {}).get("next_move"),
            }
            if arc
            else None
        ),
    }
    return [
        SystemMessage(content=INTENT_PROMPT.format(route=route or "empathy", checklist=bullets)),
        SystemMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]


def rewrite_request(draft: str, notes: list[str], last_message: str = "") -> list[BaseMessage]:
    """재작성 요청. 최종 답변의 상당수가 이 산출물이라 위기 문단과 사용자 발화를 같이 줌 —
    없으면 재작성이 초안의 상담 안내를 지워도 이후 검수가 잡지 못함."""
    bullets = "\n".join(f"- {item}" for item in notes)
    payload = json.dumps({"draft": draft, "last_message": last_message}, ensure_ascii=False)
    return [
        SystemMessage(content=REWRITE_PROMPT.format(notes=bullets) + "\n" + crisis_prompt()),
        SystemMessage(content=payload),
    ]
