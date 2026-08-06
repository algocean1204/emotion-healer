"""첫 안부의 시간 맥락. 문구가 아니라 대화의 자세만 판정함."""

from datetime import datetime

import pytest
from langchain_core.messages import AIMessage

from app import opening
from app import session


def test_timing_marks_a_new_day_after_six_and_four_hours() -> None:
    result = opening.timing(
        "2026-08-04T20:30:00+09:00",
        now=datetime.fromisoformat("2026-08-05T06:30:00+09:00"),
        timezone_name="Asia/Seoul",
    )

    assert result["kind"] == "new_day"
    assert result["period"] == "morning"


def test_timing_keeps_a_short_overnight_gap_as_continuity() -> None:
    result = opening.timing(
        "2026-08-05T04:30:00+09:00",
        now=datetime.fromisoformat("2026-08-05T06:30:00+09:00"),
        timezone_name="Asia/Seoul",
    )

    assert result["kind"] == "same_day"


def test_timing_distinguishes_three_days_and_a_week() -> None:
    three_days = opening.timing(
        "2026-08-01T12:00:00+09:00",
        now=datetime.fromisoformat("2026-08-04T13:00:00+09:00"),
        timezone_name="Asia/Seoul",
    )
    week = opening.timing(
        "2026-07-27T12:00:00+09:00",
        now=datetime.fromisoformat("2026-08-04T13:00:00+09:00"),
        timezone_name="Asia/Seoul",
    )

    assert three_days["kind"] == "three_days"
    assert week["kind"] == "week_plus"


def test_opening_key_changes_when_the_day_part_changes() -> None:
    last_contact = "2026-08-05T08:00:00+09:00"
    morning = opening.timing(
        last_contact,
        now=datetime.fromisoformat("2026-08-05T09:00:00+09:00"),
        timezone_name="Asia/Seoul",
    )
    afternoon = opening.timing(
        last_contact,
        now=datetime.fromisoformat("2026-08-05T13:00:00+09:00"),
        timezone_name="Asia/Seoul",
    )

    assert morning["key"] != afternoon["key"]


def test_next_day_morning_fallback_notices_the_morning_without_broadcast_greeting() -> None:
    assert opening._fallback("new_day", "morning") == "아침이네. 잘 잤어?"


def test_empty_session_is_a_first_visit_even_though_it_has_a_created_time() -> None:
    stored = session.empty("jiwon", "jiwon-1")

    result = opening.timing(
        opening.last_contact_at(stored),
        now=datetime.fromisoformat("2026-08-05T13:00:00+09:00"),
        timezone_name="Asia/Seoul",
    )

    assert result["kind"] == "first"


class _ReplyModel:
    def __init__(self, content: str | list[str]) -> None:
        self.contents = content if isinstance(content, list) else [content]
        self.calls = 0

    async def ainvoke(self, _messages):
        index = min(self.calls, len(self.contents) - 1)
        self.calls += 1
        return AIMessage(content=self.contents[index])


@pytest.mark.asyncio
async def test_compose_keeps_only_allowed_hypothesis_evidence() -> None:
    stored = session.empty("jiwon", "jiwon-1")
    result = await opening.compose(
        stored,
        _ReplyModel(
            '{"text":"야, 요즘 아침이 늘 빠르네. 하루가 보통 어떻게 흘러가?",'
            '"hypothesis":{"topic":"하루 리듬","evidence_ids":["n1"]}}'
        ),
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T13:00:00+09:00"),
        candidates=[{"id": "n1", "text": "아침 일찍 움직이는 편"}],
    )

    assert result["text"].startswith("야, 요즘")
    assert result["pending_hypothesis"] == {
        "topic": "하루 리듬",
        "evidence_ids": ["n1"],
        "created_at": "2026-08-05T13:00:00+09:00",
        "expires_at": "2026-08-06T13:00:00+09:00",
    }


@pytest.mark.asyncio
async def test_compose_drops_unavailable_hypothesis_evidence() -> None:
    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        _ReplyModel('{"text":"야, 왔네.","hypothesis":{"topic":"직업","evidence_ids":["missing"]}}'),
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T13:00:00+09:00"),
        candidates=[{"id": "n1", "text": "아침 일찍 움직이는 편"}],
    )

    assert result["pending_hypothesis"] is None


@pytest.mark.asyncio
async def test_compose_rewrites_a_service_like_morning_greeting() -> None:
    model = _ReplyModel(
        [
            '{"text":"좋은 아침이야. 오늘도 편하게 시작해보자.","hypothesis":null}',
            '{"text":"아침이네. 잠은 좀 잤어?"}',
        ]
    )

    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        model,
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T08:00:00+09:00"),
    )

    assert result["text"] == "아침이네. 잠은 좀 잤어?"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_compose_rewrites_a_generic_chat_service_invitation() -> None:
    model = _ReplyModel(
        [
            '{"text":"오, 왔네. 오후가 한창이네. 오늘은 무슨 얘기 해볼까?","hypothesis":null}',
            '{"text":"또 왔네. 아까보다 좀 어때?"}',
        ]
    )

    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        model,
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T14:00:00+09:00"),
        contact_at="2026-08-05T13:00:00+09:00",
    )

    assert result["text"] == "또 왔네. 아까보다 좀 어때?"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_compose_lets_the_model_rewrite_a_cold_opening() -> None:
    model = _ReplyModel(
        [
            '{"text":"아, 왔네. 반갑다.","hypothesis":null}',
            '{"ok":false,"text":"어, 왔네. 반가워."}',
        ]
    )

    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        model,
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T14:00:00+09:00"),
    )

    assert result["text"] == "어, 왔네. 반가워."
    assert model.calls == 2


@pytest.mark.asyncio
async def test_compose_never_keeps_the_known_cold_opening_when_review_misses_it() -> None:
    model = _ReplyModel(
        [
            '{"text":"아, 왔네. 반갑다.","hypothesis":null}',
            '{"ok":true}',
        ]
    )

    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        model,
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T14:00:00+09:00"),
    )

    assert result["text"] == "어, 왔네. 뭐 하고 있었어?"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_compose_uses_a_short_fallback_when_the_rewrite_is_still_service_copy() -> None:
    model = _ReplyModel(
        [
            '{"text":"좋은 아침이야. 편하게 시작해보자.","hypothesis":null}',
            '{"text":"좋은 아침이야. 오늘도 천천히 시작해보자."}',
        ]
    )

    result = await opening.compose(
        session.empty("jiwon", "jiwon-1"),
        model,
        timezone_name="Asia/Seoul",
        now=datetime.fromisoformat("2026-08-05T08:00:00+09:00"),
    )

    assert result["text"] == "아침이네. 지금 뭐 하고 있었어?"
    assert model.calls == 2


def test_hypothesis_context_exposes_only_the_retained_evidence(monkeypatch) -> None:
    stored = session.empty("jiwon", "jiwon-1")
    stored["pending_hypothesis"] = {"topic": "하루 리듬", "evidence_ids": ["n1"]}
    monkeypatch.setattr(
        opening,
        "allowed_candidates",
        lambda _user_id: [
            {"id": "n1", "text": "사용자 아침 일찍 움직이는 편."},
            {"id": "n2", "text": "사용자 공개하지 않은 다른 사실."},
        ],
    )

    context = opening.hypothesis_context(stored, "jiwon")

    assert "아침 일찍" in context
    assert "공개하지 않은" not in context
    assert "사실처럼 단정" in context


def test_hypothesis_context_drops_an_expired_hypothesis(monkeypatch) -> None:
    stored = session.empty("jiwon", "jiwon-1")
    stored["pending_hypothesis"] = {
        "topic": "하루 리듬",
        "evidence_ids": ["n1"],
        "created_at": "2026-08-04T13:00:00+09:00",
        "expires_at": "2026-08-05T13:00:00+09:00",
    }
    monkeypatch.setattr(
        opening,
        "allowed_candidates",
        lambda _user_id: [{"id": "n1", "text": "사용자 아침 일찍 움직이는 편."}],
    )

    context = opening.hypothesis_context(
        stored,
        "jiwon",
        now=datetime.fromisoformat("2026-08-06T13:00:00+09:00"),
    )

    assert context == ""
