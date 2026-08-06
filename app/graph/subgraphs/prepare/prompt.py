"""사용자 이해와 상황·정체성 질문 프롬프트."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, SystemMessage

from app.prompt import crisis_prompt, identity_line

UNDERSTAND_PROMPT = """\
사용자의 마지막 메시지를 보고 되물을지와 감정 상태를 함께 판단하세요.

## 다음 행동
- situation: {situation_hint}
- emotion: {emotion_hint}
- skip: {skip_hint}
{identity_branch}

직전 추측의 이유나 근거를 묻는 말에는 새 질문을 만들지 말고 skip을 고르세요.

## 감정 상태
- emotion: 지금 감정 (예: {emotion_examples})
- intensity: 강도 (예: {intensity_examples})
- trigger: 무엇 때문인지
- hidden: 아직 말로 못 꺼낸 것. 근거가 없으면 빈 문자열

감정을 과장하거나 사용자가 말하지 않은 진단을 만들지 마세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{{"ask":"skip|situation|emotion|identity","feeling":{{"emotion":"...","intensity":"...","trigger":"...","hidden":"..."}}}}
"""

DECIDE_IDENTITY_LINE = """\
- identity: {identity_hint}
  아직 비어 있는 슬롯: {askable}
  설문지 말투 금지. 대화 속에서 슬쩍 알아차리는 톤. 직업·학교·생활 리듬을 사실처럼 단정하지 마세요.
"""

BOUNDARY_LINE = """\
사용자가 피하고 싶다고 말한 범위: {boundaries}
그 범위를 다시 캐묻는 질문은 고르지 마세요.
"""

SITUATION_PROMPT = """\
무슨 일이 있었는지 부담 없이 이어 묻는 한 줄을 만드세요. 필요하면 먼저 짧게 받아주고,
그다음 질문 하나만 하세요. 정보를 캐내는 말투는 쓰지 마세요.
"""

IDENTITY_PROMPT = """\
아직 모르는 생활의 한 조각을 대화 흐름 속에서 자연스럽게 알아보는 한두 문장을 만드세요.

비어 있는 슬롯: {askable}
톤 예시(참고만, 그대로 쓰지 마세요): {examples}

슬롯 이름을 그대로 묻지 말고, 확인된 사실과 추측을 구분하세요.
X "직업이 뭐야?"
O "회의 많은 일이야?"

짧게, 질문 하나만, 친근한 반말. 상대가 답하기 싫으면 넘길 여지를 남기세요.
"""


def understand_request(
    messages: Sequence[BaseMessage],
    hints: dict,
    vocab: dict,
    askable: list[str] | None = None,
    boundaries: list[str] | None = None,
) -> list[BaseMessage]:
    """행동과 감정을 한 번에 판단. askable 이 비면 identity 선택지를 빼 버림."""
    identity_branch = ""
    if askable:
        identity_branch = DECIDE_IDENTITY_LINE.format(
            identity_hint=hints.get("identity_hint", ""),
            askable=", ".join(askable),
        )
    text = UNDERSTAND_PROMPT.format(
        situation_hint=hints.get("situation_hint", ""),
        emotion_hint=hints.get("emotion_hint", ""),
        skip_hint=hints.get("skip_hint", ""),
        identity_branch=identity_branch,
        emotion_examples=", ".join(vocab.get("emotion_examples", [])),
        intensity_examples=", ".join(vocab.get("intensity_examples", [])),
    )
    if boundaries:
        text += "\n" + BOUNDARY_LINE.format(boundaries=" / ".join(boundaries))
    return [SystemMessage(content=text), *messages]


def situation_request(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """상황 질문 생성 요청. 질문 하나로 턴이 끝나므로 위기 문단을 여기서도 실어야 함."""
    return [SystemMessage(content=identity_line() + SITUATION_PROMPT + "\n" + crisis_prompt()), *messages]


def identity_request(
    messages: Sequence[BaseMessage],
    askable: list[str],
    examples: list[str],
    boundaries: list[str] | None = None,
) -> list[BaseMessage]:
    """정체성 질문. 슬롯 라벨을 설문처럼 옮기지 않음."""
    text = IDENTITY_PROMPT.format(askable=", ".join(askable), examples=" / ".join(examples))
    if boundaries:
        text += "\n" + BOUNDARY_LINE.format(boundaries=" / ".join(boundaries))
    return [SystemMessage(content=identity_line() + text + "\n" + crisis_prompt()), *messages]
