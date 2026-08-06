"""이성 초안 프롬프트. 기본 → 이성 결 → persona → 위기 순서로 조립함."""

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
    arc: Arc | None = None,
) -> list[BaseMessage]:
    """초안 생성 요청."""
    text = base_prompt() + f"""
## 지금은 방법이 필요한 상황입니다

오래 알아온 친구처럼 친근한 반말로 이어서, 이미 말한 제안을 뒤집거나 같은 말을 재탕하지 마세요.
{config.get("guide", "")}
"""
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
        text += "\nnext_move 와 commitments 를 지키세요. 거절된 조언은 다시 내밀지 마세요.\n"
    text += persona_block(persona)
    text += "\n" + crisis_prompt()
    return [SystemMessage(content=text), *messages]
