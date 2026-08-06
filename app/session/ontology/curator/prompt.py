"""큐레이터 프롬프트. need·expand·judge·card 네 LLM 호출."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

NEED_PROMPT = """\
최근 대화를 봅니다. 이 사용자에게 예전에 나눈 배경 기억을 참고하는 게 지금 도움이 될지 판단하세요.
인사나 잡담처럼 배경이 필요 없는 대화면 필요 없다고 답하세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"need": true}
"""

EXPAND_PROMPT = """\
최근 대화에서 사용자가 말하려는 것을 여러 표현으로 늘리세요. 동의어, 완곡한 표현, 관련 상황까지
포함해서 별칭 사전 밖의 표현도 찾아내세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"queries": ["표현1", "표현2"]}
"""

JUDGE_PROMPT = """\
최근 대화와 지금까지 찾은 배경 후보 목록을 봅니다. 이 후보들이 대화를 이해하는 배경으로
충분한지 판단하세요. 부족하면 무엇이 더 필요한지 한 줄로 쓰세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"sufficient": false, "missing": "빠진 것 한 줄"}
"""

CARD_PROMPT = """\
아래는 사용자에게 먼저 꺼내지 않을 배경 노드 목록입니다. 각 노드가 무슨 화제인지가 아니라
그 화제를 대할 때 어떤 톤으로 말해야 하는지만 한 줄씩 뽑으세요.

이름·사건·장소 같은 구체적인 내용은 절대 넣지 마세요. "가족 화제엔 조심스럽게"처럼
태도만 남기세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"tone_lines": ["가족 화제엔 조심스럽게"]}
"""


def need_request(recent_text: str) -> list[BaseMessage]:
    return [SystemMessage(content=NEED_PROMPT), SystemMessage(content=recent_text)]


def expand_request(recent_text: str, missing: str) -> list[BaseMessage]:
    """missing이 있으면 이전 재질의에서 뭐가 빠졌는지 이어붙임."""
    payload = recent_text if not missing else f"{recent_text}\n\n이전 검색에서 빠진 것: {missing}"
    return [SystemMessage(content=EXPAND_PROMPT), SystemMessage(content=payload)]


def judge_request(recent_text: str, candidates: list[dict]) -> list[BaseMessage]:
    payload = {
        "recent": recent_text,
        "candidates": [
            {"subject": node["subject"], "predicate": node["predicate"], "object": node["object"], "tags": node["tags"]}
            for node in candidates
        ],
    }
    return [SystemMessage(content=JUDGE_PROMPT), SystemMessage(content=json.dumps(payload, ensure_ascii=False))]


def card_request(quiet_nodes: list[dict]) -> list[BaseMessage]:
    payload = [
        {"subject": node["subject"], "predicate": node["predicate"], "object": node["object"], "tags": node["tags"]}
        for node in quiet_nodes
    ]
    return [SystemMessage(content=CARD_PROMPT), SystemMessage(content=json.dumps(payload, ensure_ascii=False))]
