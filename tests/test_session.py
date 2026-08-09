"""세션 JSON 저장·로드. LLM을 타지 않음."""

import re
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage

from app import session
from app.session import store

# 대화 내용만 비교함. 생성 시각은 매번 다름
CONTENT_KEYS = ("messages", "archive", "feeling", "persona", "asked", "memory", "opened_topics")


def _content(stored: session.Session) -> dict:
    return {key: stored[key] for key in CONTENT_KEYS}  # type: ignore[literal-required]


def test_session_id_carries_owner_and_creation_time() -> None:
    made = session.new_session_id("jiwon", now=datetime(2026, 8, 4, 15, 4, 5, tzinfo=timezone.utc))

    assert re.fullmatch(r"jiwon-20260804-150405-[a-z]{3}", made)
    assert session.owner_of(made) == "jiwon"


def test_two_sessions_made_in_the_same_second_differ() -> None:
    """랜덤 꼬리가 없으면 같은 초에 두 번 누른 사용자가 남의 대화를 덮어씀."""
    now = datetime(2026, 8, 4, 15, 4, 5, tzinfo=timezone.utc)

    made = {session.new_session_id("jiwon", now=now) for _ in range(50)}

    assert len(made) > 1


def test_main_session_id_is_stable_for_a_user() -> None:
    assert session.main_session_id("jiwon") == "jiwon-main"


def test_save_then_load_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)
    original = session.empty("jiwon", "jiwon-1")
    original["messages"] = session.from_messages([HumanMessage(content="안녕")])

    session.save("jiwon-1", original)

    assert session.load("jiwon-1") == original


def test_load_returns_empty_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)

    loaded = session.load("jiwon-없는세션")

    assert _content(loaded) == _content(session.empty())
    assert loaded["user_id"] == "jiwon"  # 소유자는 id 에서 나옴


def test_load_returns_empty_when_broken(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    session.path("jiwon-2").write_text("{ 깨진 json", encoding="utf-8")

    assert _content(session.load("jiwon-2")) == _content(session.empty())


def test_load_fills_missing_keys_from_empty(tmp_path, monkeypatch) -> None:
    """부분적인 파일이어도 항상 완전한 Session을 돌려줌."""
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    session.path("jiwon-4").write_text('{"asked": true}', encoding="utf-8")

    loaded = session.load("jiwon-4")

    assert _content(loaded) == {**_content(session.empty()), "asked": True}


def test_session_starts_with_relationship_state() -> None:
    stored = session.empty("jiwon", "jiwon-1")

    assert stored["last_user_at"] is None
    assert stored["last_assistant_at"] is None
    assert stored["opening_key"] is None
    assert stored["pending_hypothesis"] is None
    assert stored["persona_turn"] is None


def test_save_creates_missing_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path / "새폴더")
    session.save("jiwon-3", session.empty("jiwon", "jiwon-3"))
    assert session.path("jiwon-3").exists()


def test_save_leaves_no_temporary_file_behind(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)

    session.save("jiwon-5", session.empty("jiwon", "jiwon-5"))

    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failed_save_does_not_destroy_the_previous_file(tmp_path, monkeypatch) -> None:
    """바로 덮어쓰면 도중에 죽었을 때 잘린 JSON 이 남고 load 가 그걸 빈 세션으로 삼킴."""
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)
    good = session.empty("jiwon", "jiwon-6")
    good["messages"] = session.from_messages([HumanMessage(content="지켜져야 하는 말")])
    session.save("jiwon-6", good)

    def explode(*args, **kwargs):
        raise OSError("쓰다가 죽었다")

    monkeypatch.setattr(store.os, "replace", explode)
    try:
        session.save("jiwon-6", session.empty("jiwon", "jiwon-6"))
    except OSError:
        pass

    assert session.load("jiwon-6")["messages"] == good["messages"]


def test_list_for_user_shows_only_that_users_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DIRECTORY", tmp_path)
    mine = session.empty("jiwon", "jiwon-20260804-150405-abc")
    mine["messages"] = session.from_messages([HumanMessage(content="내 첫 마디")])
    session.save("jiwon-20260804-150405-abc", mine)
    session.save("dahye-20260804-150406-xyz", session.empty("dahye", "dahye-20260804-150406-xyz"))

    listed = session.list_for_user("jiwon")

    assert [item["session_id"] for item in listed] == ["jiwon-20260804-150405-abc"]
    assert listed[0]["preview"] == "내 첫 마디"
    assert listed[0]["turns"] == 1


def test_message_serialization_round_trip() -> None:
    messages = [HumanMessage(content="요즘 힘들어"), AIMessage(content="많이 힘드셨겠어요")]
    stored = session.empty()
    stored["messages"] = session.from_messages(messages)

    restored = session.to_messages(stored)

    assert [message.content for message in restored] == [message.content for message in messages]
    assert [type(message) for message in restored] == [type(message) for message in messages]
