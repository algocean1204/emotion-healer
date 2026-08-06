"""온톨로지 추출 프롬프트. 요약·버림 문장에서 장기기억 노드를 뽑음."""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, SystemMessage

EXTRACT_PROMPT = """\
대화에서 요약되거나 버려지는 문장 목록을 봅니다. 프롬프트에서는 사라지지만
나중에 다시 찾아올 수 있게 장기기억 노드로 남기세요.

## 각 노드
subject(주체) · predicate(관계) · object(대상) · tags(검색용 태그 목록)
kind: observation(일어난 일) | interpretation(사용자의 판단) | intent(하려는 것). 애매하면 interpretation
span: state(상태) | event(사건)
origin: user(사용자가 직접 말함). 이 값만 쓰세요.
crisis: 자해·자살·학대를 암시하면 true
sensitivity: 민감한 개인 정보면 true
slot: 정체성 칸. 해당하면 아래 중 하나, 아니면 필드 자체를 빼세요
  - name: 호칭·이름 (어떻게 부르면 되는지)
  - day: 생활의 기반 (일·학교·구직·휴식·하루 리듬처럼 사용자가 직접 말한 맥락)
  - people: 곁의 사람
  - want: 원하는 것·이 대화에서 바라는 것
  - boundary: 하지 말 것·건드리기 싫은 것 (사용자가 명시한 것만)
extraction_confidence: 0~1. 사실인지가 아니라 이 문장에서 이렇게 뽑아낸 것이 맞는지의 확신
source_ids: 근거가 된 문장 id 목록

**저장 금지** — 나이, 성별, 결혼 여부, 종교, 병력, 소득, 상세 주소·지역.
말투·성격 관찰, 생활 패턴의 추정처럼 사용자가 직접 말하지 않은 내용은 장기기억으로
저장하지 마세요. 추론은 그 대화 안에서만 조심스럽게 확인할 수 있습니다.
예를 들어 회의 이야기를 했다고 사용자를 직장인으로, 늦게 잤다고 생활 리듬을 단정하지 마세요.

"사실/거짓"을 판정하지 마세요. 사용자의 말은 사용자의 인식 그대로 담습니다.

각 문장에 `role`이 붙어 있습니다. **`ai` 문장에서는 노드를 뽑지 마세요.** 당신이 되물은
말이지 사용자가 겪은 일이 아닙니다. `human` 문장을 해석할 문맥으로만 쓰세요.

subject는 `사용자`로 뭉치지 말고 이야기의 실제 대상을 적으세요 — 사람이면 그 사람
(`어머니`, `팀장`), 사람이 아니면 화제어(`잠`, `이직`, `돈`). 사용자 자신의 상태를
말하는 문장만 `사용자`입니다. tags에는 나중에 이 노드를 찾을 검색어를 넣으세요.

`asked_before`는 직전에 당신이 한 말입니다. **여기서는 노드를 뽑지 마세요.**
짧은 답이 무엇에 대한 답인지 푸는 데만 씁니다 —
"어떻게 불러드릴까요" 뒤의 "그냥 지원이요"는 호칭(slot=name)이지 다른 무엇이 아닙니다.

기존 활성 노드 목록도 함께 줍니다. 새 문장이 그중 하나를 뒤집으면(번복) 지우지 말고
supersedes에 {"기존 id": 새 노드의 nodes 배열 순번(0부터)} 로 표시하세요.

## 출력 형식 (JSON만, 다른 말 붙이지 마세요)
{"nodes": [{"subject": "...", "predicate": "...", "object": "...", "tags": ["..."],
"kind": "observation", "span": "state", "origin": "user", "crisis": false,
"sensitivity": false, "slot": "name", "extraction_confidence": 0.8, "source_ids": ["s3"]}],
"supersedes": {"old-node-id": 0}}
"""


def extract_request(
    sentences: list[dict], active_nodes: list[dict], context: list[str] | None = None
) -> list[BaseMessage]:
    """추출 프롬프트에 넣을 메시지. 대상 문장, 기존 활성 노드, 앞 턴 AI 발화를 보냄."""
    payload = {
        "asked_before": context or [],
        # role이 없으면 이번 턴 안에서 AI가 되물은 말과 사용자가 겪은 일을 구분할 수 없음
        "sentences": [
            {"id": sentence["id"], "role": sentence["role"], "text": sentence["text"]}
            for sentence in sentences
        ],
        "active_nodes": [
            {"id": node["id"], "subject": node["subject"], "predicate": node["predicate"], "object": node["object"]}
            for node in active_nodes
        ],
    }
    return [
        SystemMessage(content=EXTRACT_PROMPT),
        SystemMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
