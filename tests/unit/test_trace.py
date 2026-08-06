from __future__ import annotations

from uuid import uuid4

from app.llm import trace as trace_module


async def test_turn_trace_measures_overlapping_calls_without_payloads() -> None:
    ticks = iter([10.0, 10.5, 11.0, 11.5, 12.0, 14.0, 15.0, 16.0, 18.0])
    trace = trace_module.TurnTrace(clock=lambda: next(ticks))
    surface = uuid4()
    intent = uuid4()

    await trace.on_chat_model_start({}, [], run_id=surface, metadata={"langgraph_node": "surface"})
    await trace.on_chat_model_start({}, [], run_id=intent, metadata={"langgraph_node": "intent"})
    await trace.on_llm_new_token("비밀 응답", run_id=surface)
    await trace.on_llm_end(None, run_id=surface)
    await trace.on_llm_end(None, run_id=intent)
    trace.finish_response()
    trace.start_background()
    trace.finish_background()

    summary = trace.summary()

    assert summary["first_model_token_ms"] == 1500
    assert summary["user_visible_ms"] == 5000
    assert summary["llm_sum_ms"] == 4500
    assert summary["llm_wall_ms"] == 3500
    assert summary["sync_llm_calls"] == 2
    assert summary["background_ms"] == 2000
    assert [call["node"] for call in summary["calls"]] == ["surface", "intent"]
    assert "비밀 응답" not in repr(summary)


async def test_turn_trace_closes_failed_call() -> None:
    ticks = iter([1.0, 2.0, 3.0, 4.0])
    trace = trace_module.TurnTrace(clock=lambda: next(ticks))
    run_id = uuid4()

    await trace.on_chat_model_start({}, [], run_id=run_id, metadata={})
    await trace.on_llm_error(RuntimeError("secret"), run_id=run_id)
    trace.finish_response()

    summary = trace.summary()

    assert summary["calls"][0]["status"] == "error"
    assert "secret" not in repr(summary)
