"""공감 초안 프롬프트. 기본 → 공감 결 → persona → 위기 순서로 조립함."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, SystemMessage

import json

from app.prompt import base_prompt, crisis_prompt, persona_block
from app.types import Arc, Persona


def draft_request(
    messages: Sequence[BaseMessage],
    persona: Persona | None,
    config: dict,
    short_form: bool,
    arc: Arc | None = None,
) -> list[BaseMessage]:
    """초안 생성 요청. handoff both 일 때만 짧은 형식."""
    text = base_prompt() + f"""
## 지금은 공감이 필요한 상황입니다

오래 알아온 친구처럼, 친근한 반말로 이어 가세요. 처음 만난 상담사 말투는 쓰지 마세요.
{config.get("guide", "")}
"""
    if short_form:
        text += f"\n{config.get('short_form', '')}\n"
    if arc:
        text += "\n## 대화 궤적\n" + json.dumps(
            {
                "phase": arc.get("phase"),
                "trajectory": arc.get("trajectory"),
                "user_stance": arc.get("user_stance"),
                "commitments": arc.get("commitments"),
                "next_move": arc.get("next_move"),
            },
            ensure_ascii=False,
        )
        text += "\nnext_move 를 지키세요. commitments 를 뒤집거나 같은 제안을 재탕하지 마세요.\n"
    text += persona_block(persona)
    # 맨 뒤여야 함. 앞에 두면 바로 밑 "해결책을 꺼내지 마세요"가 상담 안내를 지움
    text += "\n" + crisis_prompt()
    return [SystemMessage(content=text), *messages]
