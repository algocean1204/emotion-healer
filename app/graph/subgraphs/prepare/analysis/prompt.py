"""공감 분석·감정 질문 프롬프트."""

from __future__ import annotations

import json
from collections.abc import Sequence

from langchain_core.messages import BaseMessage, SystemMessage

from app.prompt import crisis_prompt, identity_line
from app.types import Feeling

ANALYZE_PROMPT = """\
대화를 보고 지금 감정 상태를 분석하세요.

## 뽑을 항목
- emotion: 지금 감정 (예: {emotion_examples})
- intensity: 강도 (예: {intensity_examples})
- trigger: 무엇 때문인지
- hidden: 아직 말로 못 꺼낸 것

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{{"emotion": "...", "intensity": "...", "trigger": "...", "hidden": "..."}}
"""

QUESTION_PROMPT = """\
아래 감정 분석을 근거로, 어떤 마음이 가장 큰지 되묻는 한 줄을 만드세요.
짧게, 질문 하나만 하세요.
"""


def analyze_request(messages: Sequence[BaseMessage], vocab: dict) -> list[BaseMessage]:
    """감정 분석 요청."""
    text = ANALYZE_PROMPT.format(
        emotion_examples=", ".join(vocab.get("emotion_examples", [])),
        intensity_examples=", ".join(vocab.get("intensity_examples", [])),
    )
    return [SystemMessage(content=text), *messages]


def question_request(feeling: Feeling | None) -> list[BaseMessage]:
    """감정 질문 생성 요청. feeling을 그대로 근거로 넘김."""
    payload = json.dumps({"feeling": feeling}, ensure_ascii=False)
    return [
        SystemMessage(content=identity_line() + QUESTION_PROMPT + "\n" + crisis_prompt()),
        SystemMessage(content=payload),
    ]
