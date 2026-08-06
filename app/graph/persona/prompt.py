"""페르소나 생성 프롬프트. 고정 목록에서 고르지 않고 매 턴 새로 만듦."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

from app.types import Arc, Feeling, Persona, Route

PERSONA_PROMPT = """\
지금 이 사람을 어떻게 대할지 정합니다. 오래 알아온 친구로서, 말투와 관점을 정하고
이번 턴에 하지 말아야 할 것을 고르세요. 기본 말투는 친근한 반말입니다.

무엇을 할지(공감할지 조언할지)는 정하지 마세요. 누구로서, 어떻게 말할지만 정합니다.
이번 턴 전략은 이미 `{route}` 입니다. 그 전략 자체를 `forbidden`에 넣지 마세요.

## 말투 축 예시 (그대로 고르지 말고 참고만 하세요)
{tone_axes}

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{{"tone": ["..."], "view": "...", "forbidden": ["..."]}}
"""

CONTINUITY_PROMPT = """
## 직전 페르소나
{previous}

크게 바꾸지 마세요. 상황이 달라진 만큼만 조정하세요.
직전 `forbidden` 중 사용자가 명시한 금지는 유지하세요. 감정만 보고 매 턴 새로 만들지 마세요.
"""

BOUNDARY_PROMPT = """
## 사용자가 말한 경계
{boundaries}

이 항목은 `forbidden` 에 반드시 포함하세요. 빼면 안 됩니다.
"""

ARC_PROMPT = """
## 이번 대화 궤적 (이미 정해진 전략)
{arc}

- phase·trajectory·user_stance 에 맞는 말투를 고르세요
- do_not 항목은 forbidden 에 반드시 넣으세요
- next_move 를 view 에 반영하세요 (한 줄 전략)
"""


def request(
    feeling: Feeling | None,
    last_message: str,
    previous: Persona | None,
    tone_axes: list[str],
    route: Route | None = None,
    boundaries: list[str] | None = None,
    arc: Arc | None = None,
) -> list[BaseMessage]:
    """페르소나 생성 요청 메시지."""
    text = PERSONA_PROMPT.format(tone_axes=", ".join(tone_axes), route=route or "empathy")
    if previous is not None:
        text += CONTINUITY_PROMPT.format(previous=json.dumps(previous, ensure_ascii=False))
    if boundaries:
        text += BOUNDARY_PROMPT.format(boundaries=json.dumps(boundaries, ensure_ascii=False))
    if arc:
        text += ARC_PROMPT.format(arc=json.dumps(arc, ensure_ascii=False))
    context = json.dumps({"feeling": feeling, "last_message": last_message}, ensure_ascii=False)
    return [SystemMessage(content=text), SystemMessage(content=context)]
