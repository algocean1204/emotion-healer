"""영구 대화 기록과 비LLM 회상 검색."""

from datetime import datetime, timezone

from app.session import transcript


def test_transcript_keeps_exact_messages_after_working_context_changes(account) -> None:
    user_id = account["user_id"]
    first = transcript.append(user_id, "human", "전에 제주도에서 길을 잃었어")
    second = transcript.append(user_id, "ai", "그때 많이 당황했겠다")

    page = transcript.list_messages(user_id, limit=20)

    assert [message["id"] for message in page["messages"]] == [first["id"], second["id"]]
    assert [message["text"] for message in page["messages"]] == [
        "전에 제주도에서 길을 잃었어",
        "그때 많이 당황했겠다",
    ]


def test_transcript_uses_a_cursor_without_reordering_messages(account) -> None:
    user_id = account["user_id"]
    ids = [transcript.append(user_id, "human", f"메시지 {index}")["id"] for index in range(4)]

    latest = transcript.list_messages(user_id, limit=2)
    older = transcript.list_messages(user_id, before_id=latest["messages"][0]["id"], limit=2)

    assert [message["id"] for message in latest["messages"]] == ids[2:]
    assert [message["id"] for message in older["messages"]] == ids[:2]
    assert latest["has_more"] is True


def test_recall_search_ignores_assistant_paraphrases_and_finds_user_evidence(account) -> None:
    user_id = account["user_id"]
    expected = transcript.append(user_id, "human", "대학교 때 제주도에서 길을 잃었어")
    transcript.append(user_id, "ai", "제주도 얘기 기억할게")
    transcript.append(user_id, "human", "내가 전에 제주도 얘기한 거 기억나?")
    transcript.append(user_id, "human", "오늘은 그냥 피곤해")

    found = transcript.search(user_id, "내가 전에 제주도 얘기한 거 기억나?")

    assert [message["id"] for message in found] == [expected["id"]]


def test_recall_search_can_limit_a_korean_relative_date(account) -> None:
    user_id = account["user_id"]
    now = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    transcript.append(user_id, "human", "어제 점심엔 냉면 먹었어", created_at="2026-08-06T03:00:00+00:00")
    transcript.append(user_id, "human", "오늘 점심엔 김밥 먹었어", created_at="2026-08-07T03:00:00+00:00")

    found = transcript.search(user_id, "어제 점심에 뭐 먹었다고 했지?", now=now)

    assert [message["text"] for message in found] == ["어제 점심엔 냉면 먹었어"]


def test_recall_gate_only_opens_when_the_user_asks_to_check_history() -> None:
    assert transcript.needs_recall("내가 전에 제주도 얘기한 거 기억나?") is True
    assert transcript.needs_recall("전에 제주도 얘기 뭐였지?") is True
    assert transcript.needs_recall("어제 내가 뭐 먹었다고 했지?") is True
    assert transcript.needs_recall("오늘 제주도 날씨 좋다") is False
    assert transcript.needs_recall("내일 발표 전에 뭘 마지막으로 확인하면 좋을까?") is False


def test_missing_recall_asks_like_a_friend_instead_of_a_search_assistant() -> None:
    context = transcript.recall_context([])

    assert "언제 말했는지" in context
    assert "다시 얘기해줘" in context
    assert "어느 때쯤" not in context
    assert "언제쯤" not in context


def test_partial_recall_evidence_must_not_be_presented_as_certain() -> None:
    context = transcript.recall_context([
        {
            "id": 1,
            "created_at": "2026-08-07T01:00:00+00:00",
            "text": "제주도에 가고 싶어",
        }
    ])

    assert "직접 맞지 않으면" in context
    assert "다시 얘기해줘" in context
