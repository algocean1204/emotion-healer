"""여러 폴더가 함께 쓰는 타입. 프로젝트 안의 다른 모듈은 import하지 않음."""

from __future__ import annotations

from typing import Literal, TypedDict

Ask = Literal["skip", "situation", "emotion", "identity"]
Route = Literal["empathy", "reason", "both"]

OntologyKind = Literal["observation", "interpretation", "intent"]
OntologySpan = Literal["state", "event"]
OntologyOrigin = Literal["user", "inferred"]
OntologyStatus = Literal["active", "superseded", "retracted"]
OntologyDisclosure = Literal["quiet", "proactive"]
# 정체성 칸. 별도 프로필 테이블 없이 Statement.slot 하나로 담음
IdentitySlot = Literal["name", "day", "people", "want", "boundary"]


class Feeling(TypedDict):
    """공감 분석 결과."""

    emotion: str
    intensity: str
    trigger: str
    hidden: str


class Persona(TypedDict):
    """말투와 이번 턴에 하지 말 것."""

    tone: list[str]
    view: str
    forbidden: list[str]


class Arc(TypedDict):
    """멀티턴 대화 궤적. 오래 아는 친구처럼 이어가려면 턴마다 이걸 넘김."""

    phase: str
    mode: Route
    trajectory: str
    user_stance: str
    commitments: list[str]
    do_not: list[str]
    next_move: str
    handoff: bool


class Draft(TypedDict):
    """검수 루프 한 회차의 초안."""

    text: str
    score: int
    # 표면 검수 통과 여부. 점수만 보면 표면에서 떨어진 초안이 최종으로 뽑힘
    ok: bool
    notes: list[str]


class OntologyNode(TypedDict):
    """장기기억 노드. subject-predicate-object 관계 한 줄."""

    id: str
    thread_id: str
    source_message_ids: list[str]
    subject: str
    predicate: str
    object: str
    kind: OntologyKind
    span: OntologySpan
    origin: OntologyOrigin
    occurred_at: str | None
    valid_from: str | None
    valid_to: str | None
    tags: list[str]
    alias_of: str | None
    status: OntologyStatus
    superseded_by: str | None
    disclosure: OntologyDisclosure
    crisis: bool
    sensitivity: bool
    extraction_confidence: float
    salience: float
    # 정체성 칸. 없으면 None — 일반 사실 노드
    slot: IdentitySlot | None
