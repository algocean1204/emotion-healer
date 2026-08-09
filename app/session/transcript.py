"""압축하지 않는 대화 원문과, 원문 위의 비LLM 검색."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from app.auth import store as auth_store

Role = Literal["human", "ai"]
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_RECALL = re.compile(
    r"(예전에|저번에|지난번|아까|어제|그제|지난주|위에).{0,20}"
    r"(말|얘기|이야기|뭐|기억|찾|확인)|"
    r"전에.{0,20}(말|얘기|이야기).{0,10}(뭐였|기억|했지|맞지)|"
    r"(말했|얘기했|이야기했).{0,15}(기억|맞지|했지)|기억(나|해|못)"
)
_STOPWORDS = {
    "내가", "나는", "전에", "예전에", "저번에", "지난번", "아까", "어제", "그제", "지난주",
    "위에", "말한", "말했", "말했던", "얘기한", "얘기했", "이야기한", "이야기했", "기억나",
    "기억해", "기억", "뭐라고", "뭐라", "했다고", "했지", "맞지", "그거", "그런", "있는",
}


@lru_cache(maxsize=1)
def ensure_schema() -> None:
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('human', 'ai')),
                text TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'chat',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS chat_messages_user_id_id ON chat_messages (user_id, id DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS chat_messages_user_time ON chat_messages (user_id, created_at DESC)"
        )


def _row(row: tuple) -> dict:
    return {
        "id": row[0],
        "role": row[1],
        "text": row[2],
        "kind": row[3],
        "created_at": row[4].isoformat(),
    }


def append(
    user_id: str,
    role: Role,
    text: str,
    *,
    kind: str = "chat",
    created_at: str | datetime | None = None,
) -> dict:
    ensure_schema()
    stamp = datetime.fromisoformat(created_at) if isinstance(created_at, str) else created_at
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute(
            """INSERT INTO chat_messages (user_id, role, text, kind, created_at)
               VALUES (%s, %s, %s, %s, COALESCE(%s, now()))
               RETURNING id, role, text, kind, created_at""",
            (user_id, role, text, kind, stamp),
        )
        row = cursor.fetchone()
        assert row is not None
        return _row(row)


def list_messages(user_id: str, *, before_id: int | None = None, limit: int = 200) -> dict:
    ensure_schema()
    size = max(1, min(limit, 500))
    with auth_store.connect() as db, db.cursor() as cursor:
        if before_id is None:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s ORDER BY id DESC LIMIT %s""",
                (user_id, size + 1),
            )
        else:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s AND id < %s ORDER BY id DESC LIMIT %s""",
                (user_id, before_id, size + 1),
            )
        rows = cursor.fetchall()
    has_more = len(rows) > size
    return {"messages": [_row(row) for row in reversed(rows[:size])], "has_more": has_more}


def needs_recall(text: str) -> bool:
    return bool(_RECALL.search(text.strip()))


def _date_range(text: str, now: datetime) -> tuple[datetime | None, datetime | None]:
    local = now.astimezone(ZoneInfo("Asia/Seoul"))
    days = 2 if "그제" in text else 1 if "어제" in text else None
    if days is None:
        return None, None
    start = (local - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _terms(text: str) -> list[str]:
    terms = []
    for token in _TOKEN.findall(text):
        if token in _STOPWORDS:
            continue
        for suffix in ("이라고", "라고", "에서", "에게", "한테", "으로", "에는", "까지", "부터", "하고", "처럼", "보다", "이나", "이랑", "은", "는", "이", "가", "을", "를", "에", "의", "도"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                token = token[: -len(suffix)]
                break
        terms.append(token)
    return terms[:8]


def search(
    user_id: str,
    query: str,
    *,
    limit: int = 8,
    now: datetime | None = None,
) -> list[dict]:
    """사용자 원문만 찾음. 생성 모델은 검색과 순위에 관여하지 않음."""
    ensure_schema()
    start, end = _date_range(query, now or datetime.now(timezone.utc))
    terms = _terms(query)
    size = max(1, min(limit, 50))
    scan_size = min(size * 4, 200)
    patterns = [f"%{term}%" for term in terms]
    with auth_store.connect() as db, db.cursor() as cursor:
        if start and end and patterns:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s AND role = 'human'
                     AND created_at >= %s AND created_at < %s AND text ILIKE ANY(%s)
                   ORDER BY id DESC LIMIT %s""",
                (user_id, start, end, patterns, scan_size),
            )
        elif start and end:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s AND role = 'human' AND created_at >= %s AND created_at < %s
                   ORDER BY id DESC LIMIT %s""",
                (user_id, start, end, scan_size),
            )
        elif patterns:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s AND role = 'human' AND text ILIKE ANY(%s)
                   ORDER BY id DESC LIMIT %s""",
                (user_id, patterns, scan_size),
            )
        else:
            cursor.execute(
                """SELECT id, role, text, kind, created_at FROM chat_messages
                   WHERE user_id = %s AND role = 'human' ORDER BY id DESC LIMIT %s""",
                (user_id, scan_size),
            )
        found = [_row(row) for row in cursor.fetchall()]
    return [message for message in found if not needs_recall(message["text"])][:size]


def recall_context(messages: list[dict]) -> str:
    if not messages:
        return (
            "과거 대화 원문에서 직접 맞는 부분을 찾지 못했다. 기억하는 척하지 말고, "
            "친구에게 말하듯 '그거 언제 말했는지 기억나? 아니면 다시 얘기해줘.'라는 뜻으로 편하게 묻는다."
        )
    evidence = "\n".join(
        f"- [대화 #{message['id']} · {message['created_at']}] {message['text']}" for message in messages
    )
    return (
        "사용자가 예전 대화를 확인해 달라고 했다. 아래는 생성된 기억이 아니라 영구 대화 원문 검색 결과다. "
        "관련된 부분만 자연스럽게 답하고, 없는 내용은 추측하지 않는다. 질문에 답한 뒤 사용자가 요청하지 않은 "
        "허락(예: '해도 돼')이나 억지 후속 질문을 붙이지 않는다. 검색 문장과 사용자의 질문이 직접 맞지 않으면 "
        "기억한다고 단정하지 말고, 언제 말했는지 묻거나 다시 얘기해줘도 된다는 뜻으로 편하게 말한다.\n" + evidence
    )
