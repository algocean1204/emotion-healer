from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import cast

import pytest
from langchain_core.language_models import BaseChatModel

import app.main as main
from app import session


def _job(session_id: str) -> main.Job:
    return {
        "status": "running",
        "step": None,
        "notice": None,
        "text": "",
        "error": "",
        "session_id": session_id,
        "started_at": 0.0,
        "finished_at": 0.0,
        "trace": {},
    }


@pytest.mark.asyncio
async def test_failed_turn_keeps_user_message_and_retry_does_not_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "jiwon-20260805-120000-abc"
    state = {"value": session.empty("jiwon", session_id)}

    monkeypatch.setattr(main.session, "load", lambda _session_id: deepcopy(state["value"]))

    def save(_session_id: str, value: session.Session) -> None:
        state["value"] = deepcopy(value)

    monkeypatch.setattr(main.session, "save", save)
    monkeypatch.setattr(main, "_runtime", lambda _user_id: (_ for _ in ()).throw(RuntimeError("offline")))

    request = main.ChatRequest(message="오늘 너무 지쳤어", session_id=session_id)
    for job_id in ("first", "retry"):
        main.jobs = {job_id: _job(session_id)}
        await main._run(job_id, request)
        assert main.jobs[job_id]["status"] == "error"

    messages = session.to_messages(state["value"])
    assert [message.content for message in messages] == ["오늘 너무 지쳤어"]
    assert state["value"]["last_user_at"] is not None


@pytest.mark.asyncio
async def test_memory_and_compression_start_in_parallel_and_merge_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "jiwon-main"
    state = {"value": session.empty("jiwon", session_id)}
    compression_started = asyncio.Event()
    overlapped = {"value": False}

    monkeypatch.setattr(main.session, "load", lambda _session_id: deepcopy(state["value"]))

    def save(_session_id: str, value: session.Session) -> None:
        state["value"] = deepcopy(value)

    async def fake_remember(value, _llm, _user_id):
        try:
            await asyncio.wait_for(compression_started.wait(), 0.1)
            overlapped["value"] = True
        except TimeoutError:
            pass
        return {**value, "memory": {"resident": ["기억"]}}

    async def fake_compress(value, _llm, _session_id):
        compression_started.set()
        return {
            **value,
            "messages": [{"type": "human", "data": {"content": "압축된 대화"}}],
            "archive": [{"summary": "이전 대화"}],
        }

    monkeypatch.setattr(main.session, "save", save)
    monkeypatch.setattr(main, "remember", fake_remember)
    monkeypatch.setattr(main, "compress_session", fake_compress)

    await main._after_turn(session_id, "jiwon", cast(BaseChatModel, object()))

    assert overlapped["value"] is True
    assert state["value"]["memory"] == {"resident": ["기억"]}
    assert state["value"]["archive"] == [{"summary": "이전 대화"}]
    assert state["value"]["messages"][0]["data"]["content"] == "압축된 대화"


@pytest.mark.asyncio
async def test_compression_survives_memory_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "jiwon-main"
    state = {"value": session.empty("jiwon", session_id)}

    monkeypatch.setattr(main.session, "load", lambda _session_id: deepcopy(state["value"]))

    def save(_session_id: str, value: session.Session) -> None:
        state["value"] = deepcopy(value)

    async def failed_remember(*_args):
        raise RuntimeError("memory failed")

    async def fake_compress(value, _llm, _session_id):
        return {
            **value,
            "messages": [{"type": "human", "data": {"content": "압축된 대화"}}],
            "archive": [{"summary": "이전 대화"}],
        }

    monkeypatch.setattr(main.session, "save", save)
    monkeypatch.setattr(main, "remember", failed_remember)
    monkeypatch.setattr(main, "compress_session", fake_compress)

    await main._after_turn(session_id, "jiwon", cast(BaseChatModel, object()))

    assert state["value"]["archive"] == [{"summary": "이전 대화"}]


@pytest.mark.asyncio
async def test_memory_survives_compression_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "jiwon-main"
    state = {"value": session.empty("jiwon", session_id)}

    monkeypatch.setattr(main.session, "load", lambda _session_id: deepcopy(state["value"]))

    def save(_session_id: str, value: session.Session) -> None:
        state["value"] = deepcopy(value)

    async def fake_remember(value, _llm, _user_id):
        return {**value, "memory": {"resident": ["기억"]}}

    async def failed_compress(*_args):
        raise RuntimeError("compression failed")

    monkeypatch.setattr(main.session, "save", save)
    monkeypatch.setattr(main, "remember", fake_remember)
    monkeypatch.setattr(main, "compress_session", failed_compress)

    await main._after_turn(session_id, "jiwon", cast(BaseChatModel, object()))

    assert state["value"]["memory"] == {"resident": ["기억"]}
