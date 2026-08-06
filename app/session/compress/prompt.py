"""채점·요약 프롬프트. 원문 echo 없이 문장 id만 참조함."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

SCORE_PROMPT = """\
대화를 문장 단위로 쪼갠 목록을 봅니다. 각 문장을 세 축으로 채점하고 등급을 직접 정하세요.

## 채점 축 (각 0~3 정수)
- emotion: 아프게 말한 정도
- fact: 인물·사건·관계·상황 설정
- open: 아직 안 닫혔고 지금 화제와 이어지는 정도

## 등급
keep(유지) | summarize(요약) | drop(버림)

원문을 다시 쓰지 마세요. 문장 id만 참조하세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"sentences": [{"id": "s1", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "keep", "why": "짧은 이유"}]}
"""

SHRINK_PROMPT = """\
등급이 매겨진 문장 목록을 봅니다.

summarize 등급 문장 중 서로 이어지는 것을 묶어 요약문 하나로 줄이세요.
drop 등급 문장이 빠지는 자리에는 무슨 이야기가 생략됐는지 브리지 한 줄을 남기세요.

원문을 그대로 옮기지 말고 문장 id로만 참조하세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"summaries": [{"replaces": ["s3", "s4"], "text": "요약문"}], "bridges": [{"after": "s2", "text": "브리지 한 줄"}]}
"""


def score_request(sentences: list[dict]) -> list[BaseMessage]:
    """채점 프롬프트에 넣을 메시지. id와 원문만 보냄."""
    payload = [{"id": sentence["id"], "text": sentence["text"]} for sentence in sentences]
    return [
        SystemMessage(content=SCORE_PROMPT),
        SystemMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]


def shrink_request(sentences: list[dict], graded: list[dict]) -> list[BaseMessage]:
    """요약 프롬프트에 넣을 메시지. summarize·drop 등급만 추림."""
    text_by_id = {sentence["id"]: sentence["text"] for sentence in sentences}
    payload = [
        {"id": record["id"], "text": text_by_id[record["id"]], "grade": record["grade"]}
        for record in graded
        if record["grade"] in {"summarize", "drop"} and record["id"] in text_by_id
    ]
    return [
        SystemMessage(content=SHRINK_PROMPT),
        SystemMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
