from __future__ import annotations

from copy import deepcopy

import pytest

import app.main as main
from app import session


def _job(session_id: str) -> main.Job:
    return {
        "status": "running",
        "step": None,
        "text": "",
        "error": "",
        "session_id": session_id,
        "started_at": 0.0,
        "finished_at": 0.0,
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
