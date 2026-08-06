"""턴 지연 계측. 사용자 입력과 모델 출력은 기록하지 않음."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler


class TurnTrace(AsyncCallbackHandler):
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._calls: list[dict[str, Any]] = []
        self._first_token: float | None = None
        self._response_finished: float | None = None
        self._background_started: float | None = None
        self._background_finished: float | None = None
        self._phase = "response"

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del messages, kwargs
        now = self._clock()
        node = (metadata or {}).get("langgraph_node") or serialized.get("name") or "llm"
        self._runs[str(run_id)] = {
            "node": str(node),
            "phase": self._phase,
            "started": now,
        }

    async def on_llm_new_token(self, token: Any, *, run_id: UUID, **kwargs: Any) -> None:
        del token, run_id, kwargs
        if self._first_token is None:
            self._first_token = self._clock()

    async def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        del response, kwargs
        self._finish_call(run_id, "ok")

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        del error, kwargs
        self._finish_call(run_id, "error")

    def _finish_call(self, run_id: UUID, status: str) -> None:
        found = self._runs.pop(str(run_id), None)
        if found is None:
            return
        ended = self._clock()
        self._calls.append({**found, "ended": ended, "status": status})

    def finish_response(self) -> None:
        if self._response_finished is None:
            self._response_finished = self._clock()

    def start_background(self) -> None:
        self._phase = "background"
        self._background_started = self._clock()

    def finish_background(self) -> None:
        self._background_finished = self._clock()

    def summary(self) -> dict[str, Any]:
        calls = sorted(self._calls, key=lambda call: call["started"])
        public_calls = [
            {
                "node": call["node"],
                "phase": call["phase"],
                "started_ms": self._ms(call["started"] - self._started),
                "duration_ms": self._ms(call["ended"] - call["started"]),
                "status": call["status"],
            }
            for call in calls
        ]
        return {
            "user_visible_ms": self._elapsed(self._response_finished),
            "first_model_token_ms": self._elapsed(self._first_token),
            "background_ms": (
                self._ms(self._background_finished - self._background_started)
                if self._background_started is not None and self._background_finished is not None
                else None
            ),
            "sync_llm_calls": sum(call["phase"] == "response" for call in calls),
            "background_llm_calls": sum(call["phase"] == "background" for call in calls),
            "llm_sum_ms": self._ms(sum(call["ended"] - call["started"] for call in calls)),
            "llm_wall_ms": self._wall_ms(calls),
            "rewrites": sum(call["node"] in {"rewrite", "local_edit"} for call in calls),
            "calls": public_calls,
        }

    def _elapsed(self, ended: float | None) -> int | None:
        return self._ms(ended - self._started) if ended is not None else None

    @staticmethod
    def _ms(seconds: float) -> int:
        return round(seconds * 1000)

    def _wall_ms(self, calls: list[dict[str, Any]]) -> int:
        if not calls:
            return 0
        total = 0.0
        start = calls[0]["started"]
        end = calls[0]["ended"]
        for call in calls[1:]:
            if call["started"] <= end:
                end = max(end, call["ended"])
            else:
                total += end - start
                start, end = call["started"], call["ended"]
        return self._ms(total + end - start)
