"""첫 안부의 시간 맥락. 문구는 모델이, 시간의 사실은 코드가 맡음."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import SystemMessage

from app import guide
from app.session.ontology import graph_store
from app.session.store import Session


OpeningKind = Literal["first", "same_day", "new_day", "three_days", "week_plus"]
OpeningPeriod = Literal["dawn", "morning", "afternoon", "evening"]


class OpeningTiming(TypedDict):
    kind: OpeningKind
    period: OpeningPeriod
    key: str


class OpeningResult(TypedDict):
    text: str
    timing: OpeningTiming
    pending_hypothesis: dict | None


OPENING_PROMPT = """\
스트롱 민수가 채팅창을 열어 다시 온 사람에게 먼저 말을 겁니다. 오래 알고 지낸 친구처럼
편하게 말하되, 실제로 확인된 사실보다 더 아는 척하지는 마세요.
스트롱 민수는 당신의 이름입니다. 사용자 호칭은 확인 전까지 모릅니다. 상대를 민수라고 부르지 마세요.

시간 간격과 시간대는 소재를 고를 때의 힌트일 뿐입니다. 밥, 날씨, 직업, 이전 화제를
반드시 언급할 필요가 없습니다. 질문을 아예 하지 않고 자연스럽게 인사해도 됩니다.
간격이 first면 실제 첫 만남이므로 "다시", "또", "오랜만" 같은 재방문 표현을 쓰지 마세요.
간격이 week_plus면 오랜만이라는 뜻은 자연스럽게 드러내세요.

한국어 친구 말투는 시간을 알려 주거나 하루의 태도를 지도하는 안내 문구와 다릅니다.
아침을 굳이 말한다면 "좋은 아침이야"보다 "아침이네"처럼 지금을 함께 알아차리세요.
"좋은 아침이야. 오늘도 편하게 시작해보자."처럼 시간 인사 뒤에 시작 방식을 권하는
두 문장 구조는 쓰지 마세요. "편하게 시작", "천천히 시작", "시작해보자"도 쓰지 마세요.
"오후가 한창이네", "오늘은 무슨 얘기 해볼까"처럼 시간을 방송하고 대화 주제를 고르게 하는
진행자 문장도 쓰지 마세요. 친구는 채팅을 운영하지 않고, 보고 싶던 사람에게 그냥 말을 겁니다.

주어진 기억은 사용자가 먼저 꺼내도 된다고 허용한 사실뿐입니다. 한 번에 하나만 살짝
활용할 수 있고, 목록처럼 나열하거나 "왜 안 왔어"라고 묻지 마세요. 직업·생활 리듬을
짐작할 수 있어도 사실처럼 단정하지 말고, 말 속에서 확인할 여지가 있을 때만 넓게 물으세요.

출력은 JSON 하나입니다.
{"text":"친구처럼 자연스러운 첫 말", "hypothesis":{"topic":"확인 전 가설의 주제", "evidence_ids":["허용 기억 id"]} 또는 null}
"""

OPENING_REVIEW_PROMPT = """\
아래 첫말 전체를 실제 한국인 친구의 말로 검수하세요. 특정 단어 하나로 판정하거나 정해진
문장 틀에 맞추지 말고, 이 조합과 호흡이 상대에게 어떻게 들리는지 보세요.

- 친근한 말을 썼어도 무심하거나 퉁명스럽고 내려다보는 인상이면 다시 씁니다.
- 서비스 진행자처럼 시간을 방송하거나 대화 주제를 고르게 하면 다시 씁니다.
- 하루의 태도를 정해 주거나 질문으로 답을 재촉하면 다시 씁니다.
- 과장된 반가움이나 상담 말투를 보태지 말고, 짧지만 온기가 느껴지는 생활어를 씁니다.

그대로 자연스러우면 {"ok":true}, 고쳐야 하면 {"ok":false,"text":"고친 첫말"}만 출력하세요.
"""

_KNOWN_BAD_OPENING_PHRASES = (
    "좋은 아침",
    "편하게 시작",
    "천천히 시작",
    "시작해보자",
    "함께 시작",
    "오후가 한창",
    "얘기 해볼까",
    "아, 왔네. 반갑다",
)


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Seoul")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _period(hour: int) -> OpeningPeriod:
    if hour < 6:
        return "dawn"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def last_contact_at(session: Session) -> str | None:
    """기억 저장 시각이 아니라 실제 사람·민수 발화 중 가장 최근 시각을 씀."""
    values = [_parse_time(session.get(key)) for key in ("last_user_at", "last_assistant_at")]
    known = [value for value in values if value is not None]
    if known:
        return max(known).isoformat()
    if not session.get("messages"):
        return None
    return session.get("updated_at") or session.get("created_at")


def latest_contact_at(sessions: Sequence[Session]) -> str | None:
    """여러 대화 중 실제로 가장 최근에 끝난 대화 시각을 고름."""
    known = [_parse_time(last_contact_at(session)) for session in sessions]
    contacts = [value for value in known if value is not None]
    return max(contacts).isoformat() if contacts else None


def timing(
    last_contact_at: str | None,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Seoul",
) -> OpeningTiming:
    """재방문 자세를 정함. 시간대는 소재의 힌트일 뿐 문구를 강제하지 않음."""
    zone = _zone(timezone_name)
    local_now = (now or datetime.now(zone)).astimezone(zone)
    period = _period(local_now.hour)
    previous = _parse_time(last_contact_at)
    if previous is None:
        return {"kind": "first", "period": period, "key": f"{local_now.date()}:{period}"}

    local_previous = previous.astimezone(zone)
    elapsed_hours = max((local_now - local_previous).total_seconds() / 3600, 0)
    if elapsed_hours >= 24 * 7:
        kind: OpeningKind = "week_plus"
    elif elapsed_hours >= 24 * 3:
        kind = "three_days"
    elif (
        local_now.date() > local_previous.date()
        and local_now.hour >= 6
        and elapsed_hours >= 4
    ):
        kind = "new_day"
    else:
        kind = "same_day"
    return {
        "kind": kind,
        "period": period,
        "key": f"{local_now.date()}:{period}",
    }


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fallback(kind: OpeningKind, period: OpeningPeriod) -> str:
    if period == "morning":
        morning = {
            "first": "아침이네. 지금 뭐 하고 있었어?",
            "same_day": "또 왔네. 아까보다 좀 어때?",
            "new_day": "아침이네. 잘 잤어?",
            "three_days": "아침이네. 며칠 사이 어떻게 지냈어?",
            "week_plus": "오랜만이네. 잘 지냈어?",
        }
        return morning[kind]
    return {
        "first": "어, 왔네. 뭐 하고 있었어?",
        "same_day": "또 왔네. 아까보다 좀 어때?",
        "new_day": "왔네. 오늘은 좀 어땠어?",
        "three_days": "며칠 만이네. 그동안 잘 지냈어?",
        "week_plus": "오랜만이다. 그동안 어떻게 지냈어?",
    }[kind]


def _needs_opening_rewrite(text: str) -> bool:
    return any(phrase in text for phrase in _KNOWN_BAD_OPENING_PHRASES)


def allowed_candidates(user_id: str) -> list[dict]:
    """사용자가 먼저 꺼내도 좋다고 한 사실만 첫 안부의 근거로 보냄."""
    allowed = []
    for node in graph_store.nodes(user_id):
        if (
            node.get("status") != "active"
            or node.get("origin") != "user"
            or node.get("disclosure") != "proactive"
            or node.get("sensitivity")
            or node.get("crisis")
        ):
            continue
        allowed.append(
            {
                "id": node["id"],
                "text": f"{node['subject']} {node['predicate']} {node['object']}.",
            }
        )
    return allowed[:3]


def hypothesis_context(session: Session, user_id: str, *, now: datetime | None = None) -> str:
    """확인 전 가설을 다음 발화에서만 투명하게 설명할 수 있게 함."""
    pending = session.get("pending_hypothesis")
    if not isinstance(pending, dict):
        return ""
    expires_at = pending.get("expires_at")
    if expires_at:
        try:
            expires = datetime.fromisoformat(str(expires_at))
        except ValueError:
            return ""
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= (now or datetime.now(timezone.utc)):
            return ""
    evidence_ids = {str(item) for item in pending.get("evidence_ids", [])}
    evidence = [item["text"] for item in allowed_candidates(user_id) if item["id"] in evidence_ids]
    topic = str(pending.get("topic", "")).strip()
    if not topic or not evidence:
        return ""
    return (
        "직전 첫 안부에서 확인 전 가설을 조심스럽게 떠올렸습니다. "
        f"주제: {topic}. 근거: {' '.join(evidence)} "
        "사용자가 왜 그렇게 생각했는지 직접 묻거나 확인할 때만, 이 근거를 한두 문장으로 솔직하게 말하세요. "
        "가설을 사실처럼 단정하거나 새 기억으로 저장하지 마세요."
    )


async def compose(
    session: Session,
    llm: Any,
    *,
    timezone_name: str = "Asia/Seoul",
    now: datetime | None = None,
    candidates: list[dict] | None = None,
    contact_at: str | None = None,
) -> OpeningResult:
    """한 번의 작성 모델 호출로 첫 안부와 확인 전 가설을 만듦."""
    current = now or datetime.now(timezone.utc)
    timing_result = timing(contact_at or last_contact_at(session), now=current, timezone_name=timezone_name)
    allowed = candidates or []
    payload = {
        "재방문 맥락": {"간격": timing_result["kind"], "시간대": timing_result["period"]},
        "허용 기억": [{"id": item.get("id"), "text": item.get("text")} for item in allowed],
    }
    answer = await llm.ainvoke(
        [SystemMessage(content=OPENING_PROMPT), SystemMessage(content=json.dumps(payload, ensure_ascii=False))]
    )
    parsed = _parse_json(str(answer.content))
    text = str(parsed.get("text", "")).strip()
    if text:
        review = await llm.ainvoke(
            [
                SystemMessage(content=OPENING_REVIEW_PROMPT),
                SystemMessage(
                    content=json.dumps(
                        {"첫말": text, "재방문 맥락": payload["재방문 맥락"]},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        reviewed = _parse_json(str(review.content))
        review_text = str(reviewed.get("text", "")).strip()
        review_ok = reviewed.get("ok")
        rejected = review_ok is False or str(review_ok).strip().lower() in {"false", "no", "0"}
        if rejected:
            text = review_text
        elif review_ok is None and review_text:
            text = review_text
    if not text or _needs_opening_rewrite(text):
        text = _fallback(timing_result["kind"], timing_result["period"])

    hypothesis = parsed.get("hypothesis")
    allowed_ids = {str(item.get("id")) for item in allowed if item.get("id")}
    pending: dict | None = None
    if isinstance(hypothesis, dict):
        topic = str(hypothesis.get("topic", "")).strip()
        evidence_ids = [str(item) for item in hypothesis.get("evidence_ids", []) if str(item) in allowed_ids]
        if topic and evidence_ids:
            config = guide.load(graph_store.__file__, "healer_ontology.json")
            ttl = int(config.get("hypothesis_ttl_seconds", 86400))
            pending = {
                "topic": topic,
                "evidence_ids": evidence_ids,
                "created_at": current.isoformat(),
                "expires_at": (current + timedelta(seconds=ttl)).isoformat(),
            }
    return {"text": text, "timing": timing_result, "pending_hypothesis": pending}
