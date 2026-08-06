"""대화 세션 저장. checkpointer 대신 이 JSON이 유일한 진실임.

사용자마다 여러 세션 보유. 기억(온톨로지)은 세션이 아니라 사용자에 붙음 —
새 대화를 열 때마다 AI가 사람을 처음 보면 안 되기 때문임.
"""

from __future__ import annotations

import json
import os
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict

from app.types import Arc, Feeling, Persona

DIRECTORY = Path(__file__).resolve().parents[2] / "sessions"
SUFFIX_LENGTH = 3


class Session(TypedDict):
    user_id: str
    session_id: str
    created_at: str
    updated_at: str  # 목록 정렬용. 마지막 저장 시각
    messages: list[dict]
    archive: list[dict]
    feeling: Feeling | None
    persona: Persona | None
    asked: bool
    memory: dict  # 큐레이터가 채움. v2는 candidate_ids·tone_lines·만료 시각
    opened_topics: list[str]  # 세션 안에서 사용자가 직접 꺼낸 화제 태그
    identity_asks: int  # 이 세션에서 정체성 질문을 낸 횟수
    last_identity_turn: int | None  # 마지막 정체성 질문 시점의 human 턴 번호
    arc: Arc | None  # 직전 답변 턴의 대화 궤적. orient 가 읽어 이어감
    last_user_at: str | None  # 실제 사용자 발화 시각. 저장 작업 시각과 다름
    last_assistant_at: str | None  # 실제 답변·첫 안부가 끝난 시각
    opening_key: str | None  # 같은 시간대에 첫 안부를 반복하지 않는 키
    pending_hypothesis: dict | None  # 확인 전 추측. 근거 id·만료 시각과 함께 세션에만 둠

def new_session_id(user_id: str, now: datetime | None = None) -> str:
    """<user_id>-<YYYYMMDD-HHMMSS>-<abc>. 시각은 서버가 찍음 —
    클라이언트가 정하면 위조되고 시계가 어긋남."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase, k=SUFFIX_LENGTH))
    return f"{user_id}-{stamp}-{suffix}"


def owner_of(session_id: str) -> str:
    """세션 id 앞부분으로 소유자 판정. 다른 사용자의 세션 접근 차단."""
    return session_id.split("-", 1)[0]


def path(session_id: str) -> Path:
    return DIRECTORY / f"healer_session_{session_id}.json"


def empty(user_id: str = "", session_id: str = "") -> Session:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": user_id,
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "archive": [],
        "feeling": None,
        "persona": None,
        "asked": False,
        "memory": {},
        "opened_topics": [],
        "identity_asks": 0,
        "last_identity_turn": None,
        "arc": None,
        "last_user_at": None,
        "last_assistant_at": None,
        "opening_key": None,
        "pending_hypothesis": None,
    }


def load(session_id: str) -> Session:
    """파일이 없거나 깨져 있으면 빈 세션으로 시작함. 빠진 키는 empty() 값으로 메움."""
    base = empty(owner_of(session_id), session_id)
    try:
        raw = json.loads(path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return base
    if not isinstance(raw, dict):
        return base
    return {
        "user_id": raw.get("user_id", base["user_id"]),
        "session_id": raw.get("session_id", base["session_id"]),
        "created_at": raw.get("created_at", base["created_at"]),
        "updated_at": raw.get("updated_at") or raw.get("created_at", base["updated_at"]),
        "messages": raw.get("messages", base["messages"]),
        "archive": raw.get("archive", base["archive"]),
        "feeling": raw.get("feeling", base["feeling"]),
        "persona": raw.get("persona", base["persona"]),
        "asked": raw.get("asked", base["asked"]),
        "memory": raw.get("memory", base["memory"]),
        "opened_topics": raw.get("opened_topics", base["opened_topics"]),
        "identity_asks": int(raw.get("identity_asks", base["identity_asks"]) or 0),
        "last_identity_turn": raw.get("last_identity_turn", base["last_identity_turn"]),
        "arc": raw.get("arc", base["arc"]),
        "last_user_at": raw.get("last_user_at", base["last_user_at"]),
        "last_assistant_at": raw.get("last_assistant_at", base["last_assistant_at"]),
        "opening_key": raw.get("opening_key", base["opening_key"]),
        "pending_hypothesis": raw.get("pending_hypothesis", base["pending_hypothesis"]),
    }


def save(session_id: str, session: Session) -> None:
    """임시 파일에 쓰고 바꿔치움. 바로 쓰면 도중에 죽었을 때 잘린 JSON이 남고,
    load()가 그걸 삼켜서 기억이 통째로 사라진 것처럼 보임."""
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    target = path(session_id)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)


def remove(session_id: str) -> None:
    """대화만 지움. 기억은 사람에 붙어 있어 여기서 안 없어짐."""
    path(session_id).unlink(missing_ok=True)


def list_for_user(user_id: str) -> list[dict]:
    """그 사용자의 세션 목록. 최근에 쓴 것부터(updated_at)."""
    found = []
    for file in DIRECTORY.glob(f"healer_session_{user_id}-*.json"):
        session_id = file.stem.removeprefix("healer_session_")
        session = load(session_id)
        if session["user_id"] != user_id:
            continue  # 아이디 앞부분만 같은 남의 세션
        first = next(
            (
                str(message.get("data", {}).get("content", ""))
                for message in session["messages"]
                if message.get("type") == "human"
            ),
            "",
        )
        found.append(
            {
                "session_id": session_id,
                "created_at": session["created_at"],
                "updated_at": session.get("updated_at") or session["created_at"],
                "preview": first[:40],
                "turns": sum(1 for m in session["messages"] if m.get("type") == "human"),
            }
        )
    return sorted(found, key=lambda item: item["updated_at"], reverse=True)


def to_messages(session: Session) -> list[BaseMessage]:
    return messages_from_dict(session["messages"])


def from_messages(messages: list[BaseMessage]) -> list[dict]:
    return messages_to_dict(messages)
