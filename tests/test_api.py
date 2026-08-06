"""채팅 API 스모크 테스트. 그래프를 스텁으로 교체해 LLM 호출 제외."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import app.main as main
from app import opening
from app.auth import store as auth_store
from app.session import store


class StubGraph:
    """실제 그래프 대신 정해둔 노드 이름·업데이트 순서를 그대로 흘려보냄."""

    def __init__(self, reply: str, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.received: list[dict] = []
        self.received_kwargs: list[dict[str, Any]] = []

    async def astream(self, inputs: dict, **kwargs: Any) -> AsyncIterator[tuple[tuple[str, ...], dict]]:
        self.received.append(inputs)
        self.received_kwargs.append(kwargs)
        yield ("sub",), {"decide": {}}
        yield ("sub",), {"route": {}}
        yield ("sub",), {"write": {}}
        await asyncio.sleep(0.05)  # 폴링이 running 상태를 관찰할 여유를 줌
        if self.error:
            raise self.error
        ai = AIMessage(content=self.reply)
        yield (), {"empathy": {"messages": [*inputs["messages"], ai], "asked": False}}


@pytest.fixture
def graph(monkeypatch):
    stub = StubGraph(reply="많이 힘드셨겠어요.")
    # 전역 graph 가 없어진 뒤에도 스텁을 끼울 수 있게 raising=False
    monkeypatch.setattr(main, "graph", stub, raising=False)
    # jobs는 프로세스 전역이라 테스트끼리 세션이 겹치면 이전 잡이 새어 들어옴
    monkeypatch.setattr(main, "jobs", {})
    monkeypatch.setattr(main, "_running_tasks", set())
    monkeypatch.setattr(main, "_tasks_by_job", {})
    monkeypatch.setattr(main, "_runtime_cache", {})
    return stub


def _poll(client: TestClient, job_id: str, tries: int = 100, delay: float = 0.01) -> dict:
    """running이 아닌 상태가 나올 때까지 기다림."""
    for _ in range(tries):
        status = client.get(f"/api/chat/{job_id}").json()
        if status["status"] != "running":
            return status
        time.sleep(delay)
    raise AssertionError("job never left running")


def _send(client: TestClient, session_id: str, message: str) -> str:
    response = client.post("/api/chat", json={"message": message, "session_id": session_id})
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


# -- 인증 -------------------------------------------------------------------


def test_endpoints_reject_anonymous_callers() -> None:
    with TestClient(main.app) as client:
        assert client.get("/api/sessions").status_code == 401
        assert client.get("/api/memory").status_code == 401
        assert client.post("/api/chat", json={"message": "x", "session_id": "a-b"}).status_code == 401


def test_wrong_verify_code_blocks_login(account) -> None:
    with TestClient(main.app) as client:
        response = client.post(
            "/api/auth/login",
            json={"user_id": account["user_id"], "password": account["password"], "code": "코드아님"},
        )
        assert response.status_code == 401


def test_wrong_code_and_wrong_password_are_indistinguishable(account) -> None:
    """무엇이 틀렸는지 알려주면 코드와 비밀번호를 따로 공략할 수 있음."""
    with TestClient(main.app) as client:
        bad_code = client.post(
            "/api/auth/login",
            json={"user_id": account["user_id"], "password": account["password"], "code": "코드아님"},
        )
        bad_password = client.post(
            "/api/auth/login",
            json={"user_id": account["user_id"], "password": "틀림", "code": auth_store.invite_code()},
        )

    assert bad_code.status_code == bad_password.status_code == 401
    assert bad_code.json()["detail"] == bad_password.json()["detail"]


def test_wrong_password_does_not_reveal_whether_the_id_exists(account) -> None:
    with TestClient(main.app) as client:
        missing = client.post(
            "/api/auth/login", json={"user_id": "nobodyhere", "password": "x", "code": auth_store.invite_code()}
        )
        wrong = client.post(
            "/api/auth/login",
            json={"user_id": account["user_id"], "password": "틀림", "code": auth_store.invite_code()},
        )
        assert missing.status_code == wrong.status_code == 401
        assert missing.json()["detail"] == wrong.json()["detail"]


def test_password_is_never_stored_in_the_clear(account) -> None:
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT password_hash FROM users WHERE user_id = %s", (account["user_id"],)
        )
        row = cursor.fetchone()

    assert row is not None
    assert account["password"] not in row[0]


def test_logout_kills_the_token(client) -> None:
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/sessions").status_code == 401


# -- 세션 소유권 -------------------------------------------------------------


def test_a_user_only_sees_their_own_sessions(client, session_id) -> None:
    listed = client.get("/api/sessions").json()["sessions"]

    assert [item["session_id"] for item in listed] == [session_id]
    assert session_id.startswith(client.user_id)


def test_another_users_session_is_not_found(client) -> None:
    assert client.get("/api/sessions/somebodyelse-20260804-150405-abc").status_code == 404
    response = client.post(
        "/api/chat", json={"message": "남의 세션", "session_id": "somebodyelse-2026-abc"}
    )
    assert response.status_code == 404


def test_delete_removes_the_session_from_the_list(client, session_id) -> None:
    assert client.delete(f"/api/sessions/{session_id}").status_code == 204

    assert client.get("/api/sessions").json()["sessions"] == []


def test_delete_of_another_users_session_is_not_found(client) -> None:
    assert client.delete("/api/sessions/somebodyelse-20260804-150405-abc").status_code == 404


# -- 채팅 --------------------------------------------------------------------


def test_post_returns_job_id_immediately(client, session_id, graph) -> None:
    response = client.post("/api/chat", json={"message": "요즘 힘들어", "session_id": session_id})

    assert response.status_code == 202
    assert response.json()["job_id"]


def test_opening_starts_and_persists_an_assistant_turn(client, session_id, monkeypatch) -> None:
    async def compose(_stored: dict, _llm: Any, **_kwargs: Any) -> dict:
        return {
            "text": "야, 왔네. 오늘은 좀 어때?",
            "timing": {"kind": "first", "period": "afternoon", "key": "2026-08-05:afternoon"},
            "pending_hypothesis": {"topic": "하루 리듬", "evidence_ids": ["n1"]},
        }

    monkeypatch.setattr(opening, "compose", compose)
    monkeypatch.setattr(opening, "allowed_candidates", lambda _user_id: [], raising=False)

    response = client.post(f"/api/sessions/{session_id}/opening", json={"timezone": "Asia/Seoul"})

    assert response.status_code == 202, response.text
    final = _poll(client, response.json()["job_id"])
    stored = store.load(session_id)
    assert final == {"status": "done", "text": "야, 왔네. 오늘은 좀 어때?"}
    assert stored["messages"][-1]["data"]["content"] == "야, 왔네. 오늘은 좀 어때?"
    assert stored["last_assistant_at"] is not None
    assert stored["opening_key"] == "2026-08-05:afternoon"
    assert stored["pending_hypothesis"] == {"topic": "하루 리듬", "evidence_ids": ["n1"]}


def test_opening_job_keeps_its_own_waiting_step(client, session_id, monkeypatch) -> None:
    async def compose(_stored: dict, _llm: Any, **_kwargs: Any) -> dict:
        await asyncio.sleep(0.05)
        return {
            "text": "야, 왔네.",
            "timing": {"kind": "first", "period": "afternoon", "key": "opening-step"},
            "pending_hypothesis": None,
        }

    monkeypatch.setattr(opening, "compose", compose)
    monkeypatch.setattr(opening, "allowed_candidates", lambda _user_id: [], raising=False)

    response = client.post(f"/api/sessions/{session_id}/opening", json={"timezone": "Asia/Seoul"})
    running = client.get(f"/api/chat/{response.json()['job_id']}").json()

    assert running == {"status": "running", "step": "채팅창 여는 중…"}


def test_opening_is_not_repeated_in_the_same_time_band(client, session_id, monkeypatch) -> None:
    async def compose(_stored: dict, _llm: Any, **_kwargs: Any) -> dict:
        return {
            "text": "야, 왔네.",
            "timing": {"kind": "first", "period": "afternoon", "key": "same-band"},
            "pending_hypothesis": None,
        }

    monkeypatch.setattr(opening, "compose", compose)
    monkeypatch.setattr(opening, "allowed_candidates", lambda _user_id: [], raising=False)
    monkeypatch.setattr(
        opening,
        "timing",
        lambda *_args, **_kwargs: {"kind": "first", "period": "afternoon", "key": "same-band"},
    )

    first = client.post(f"/api/sessions/{session_id}/opening", json={"timezone": "Asia/Seoul"})
    assert first.status_code == 202, first.text
    _poll(client, first.json()["job_id"])

    second = client.post(f"/api/sessions/{session_id}/opening", json={"timezone": "Asia/Seoul"})

    assert second.status_code == 200
    assert second.json() == {"needed": False}


def test_opening_is_not_appended_to_an_untouched_assistant_only_session(
    client, session_id, monkeypatch
) -> None:
    stored = store.load(session_id)
    stored["messages"] = store.from_messages([AIMessage(content="먼저 건넨 첫말")])
    stored["last_assistant_at"] = "2026-08-06T00:30:00+00:00"
    stored["opening_key"] = "2026-08-06:morning"
    store.save(session_id, stored)
    monkeypatch.setattr(
        opening,
        "timing",
        lambda *_args, **_kwargs: {
            "kind": "same_day",
            "period": "afternoon",
            "key": "2026-08-06:afternoon",
        },
    )

    response = client.post(f"/api/sessions/{session_id}/opening", json={"timezone": "Asia/Seoul"})

    assert response.status_code == 200
    assert response.json() == {"needed": False}
    assert [message.content for message in store.to_messages(store.load(session_id))] == [
        "먼저 건넨 첫말"
    ]


def test_memory_edit_returns_a_rebuilt_graph(client) -> None:
    main.ontology_graph.add(
        client.user_id,
        [
            {
                "id": "edit-me",
                "thread_id": client.user_id,
                "source_message_ids": [],
                "subject": "사용자",
                "predicate": "겪고 있음",
                "object": "잠이 오지 않음",
                "kind": "observation",
                "span": "state",
                "origin": "user",
                "occurred_at": None,
                "valid_from": "2026-08-06T00:00:00+00:00",
                "valid_to": None,
                "tags": ["잠"],
                "alias_of": None,
                "status": "active",
                "superseded_by": None,
                "disclosure": "quiet",
                "crisis": False,
                "sensitivity": False,
                "extraction_confidence": 0.9,
                "salience": 0.8,
                "slot": None,
            }
        ],
    )

    response = client.post(
        "/api/memory/edit-me/edit",
        json={"subject": "사용자", "predicate": "좋아한다", "object": "저녁 산책"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["nodes"] == [
        {
            "id": "edit-me",
            "subject": "사용자",
            "predicate": "좋아한다",
            "object": "저녁 산책",
            "slot": None,
            "disclosure": "quiet",
            "crisis": False,
            "status": "active",
        }
    ]
    assert {item["label"] for item in response.json()["graph"]["entities"]} == {
        "사용자",
        "저녁 산책",
    }


def test_memory_edit_rejects_blank_ontology_parts(client) -> None:
    response = client.post(
        "/api/memory/missing/edit",
        json={"subject": " ", "predicate": "좋아한다", "object": "산책"},
    )

    assert response.status_code == 422


def test_job_reports_running_then_done_with_text(client, session_id, graph) -> None:
    job_id = _send(client, session_id, "요즘 힘들어")

    assert client.get(f"/api/chat/{job_id}").json()["status"] == "running"
    assert _poll(client, job_id) == {"status": "done", "text": "많이 힘드셨겠어요."}


def test_chat_turn_attaches_private_timing_trace(client, session_id, graph) -> None:
    job_id = _send(client, session_id, "요즘 힘들어")

    assert _poll(client, job_id) == {"status": "done", "text": "많이 힘드셨겠어요."}
    callbacks = graph.received_kwargs[0]["config"]["callbacks"]
    assert callbacks[0].__class__.__name__ == "TurnTrace"
    assert main.jobs[job_id]["trace"]["user_visible_ms"] >= 0


def test_session_persists_and_next_request_loads_history(client, session_id, graph) -> None:
    graph.reply = "첫 답"
    _poll(client, _send(client, session_id, "첫 메시지"))

    assert store.path(session_id).exists()
    assert store.load(session_id)["last_user_at"] is not None
    assert store.load(session_id)["last_assistant_at"] is not None

    graph.reply = "둘째 답"
    _poll(client, _send(client, session_id, "둘째 메시지"))

    contents = [message.content for message in graph.received[1]["messages"]]
    assert contents == ["첫 메시지", "첫 답", "둘째 메시지"]


def test_two_sessions_of_one_user_do_not_share_history(client, session_id, graph) -> None:
    """세션마다 대화가 다름. 기억만 사람을 따라감."""
    other = client.post("/api/sessions").json()["session_id"]
    graph.reply = "첫 답"
    _poll(client, _send(client, session_id, "첫 세션 메시지"))

    _poll(client, _send(client, other, "둘째 세션 메시지"))

    contents = [message.content for message in graph.received[-1]["messages"]]
    assert contents == ["둘째 세션 메시지"]


def test_graph_error_becomes_error_status_not_stuck_running(client, session_id, graph) -> None:
    graph.error = RuntimeError("그래프 오류")

    final = _poll(client, _send(client, session_id, "요즘 힘들어"))

    assert final["status"] == "error"


def test_error_message_never_leaks_the_exception(client, session_id, graph) -> None:
    """예외 원문이 감정 지원 화면에 그대로 뜨면 안 됨. 원인은 로그에만 남음."""
    graph.error = RuntimeError("Couldn't connect to localhost:7687")

    final = _poll(client, _send(client, session_id, "요즘 힘들어"))

    assert "RuntimeError" not in final["error"]
    assert "localhost" not in final["error"]
    assert final["error"] == "답변을 만들지 못했어요. 다시 보내주세요."


def test_compression_failure_still_leaves_a_normal_response(
    client, session_id, graph, monkeypatch
) -> None:
    async def _broken_compress(stored: dict, llm: Any, key: str, budget: int = 0) -> dict:
        raise RuntimeError("압축 실패")

    monkeypatch.setattr(main, "compress_session", _broken_compress)
    graph.reply = "답변"

    final = _poll(client, _send(client, session_id, "요즘 힘들어"))

    assert final == {"status": "done", "text": "답변"}
    assert store.load(session_id)["messages"][-1]["data"]["content"] == "답변"


def test_unknown_job_id_is_404(client) -> None:
    assert client.get("/api/chat/does-not-exist").status_code == 404


def test_duplicate_session_reuses_the_running_job(client, session_id, graph) -> None:
    first = client.post("/api/chat", json={"message": "메시지", "session_id": session_id})
    second = client.post("/api/chat", json={"message": "다른 메시지", "session_id": session_id})

    job_id = first.json()["job_id"]
    assert job_id == second.json()["job_id"]

    _poll(client, job_id)
    assert len(graph.received) == 1  # 그래프 한 번만 실행


def test_cancel_frees_the_session_for_the_next_message(client, session_id, graph) -> None:
    """취소가 잡만 남기면 다음 메시지가 중복 방지에 걸려 조용히 버려짐."""
    first = _send(client, session_id, "첫 번째")
    client.post(f"/api/chat/{first}/cancel")

    assert client.get(f"/api/chat/{first}").status_code == 404
    second = _send(client, session_id, "두 번째")
    assert second != first

    _poll(client, second)
    sent = [str(message.content) for message in graph.received[-1]["messages"]]
    assert "두 번째" in sent


def test_cancel_unknown_job_is_404(client) -> None:
    assert client.post("/api/chat/없는아이디/cancel").status_code == 404
