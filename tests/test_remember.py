"""턴 뒤 기억 만들기. 압축과 독립 실행하며 마커로 구분한 가짜 모델만 사용."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.session import store as session_module
from app.session.compress import graph as compress_graph
from app.session.compress import run as compress_run
from app.session.ontology import graph_store
from app.session.ontology.curator import graph as curator_graph
from app.session.remember import remember

CURATOR_CONFIG = {"curator_max_rounds": 3, "curator_candidate_limit": 5, "curator_recent_messages": 4}

_MARKERS = {
    "장기기억 노드": "extract",
    "배경 기억을 참고하는": "need",
    "별칭 사전 밖의 표현": "expand",
    "배경 후보 목록": "judge",
    "톤으로 말해야 하는지": "card",
}

_EXTRACTED = json.dumps(
    {
        "nodes": [
            {
                "subject": "직장 상사",
                "predicate": "질책한다",
                "object": "회의마다",
                "kind": "observation",
                "span": "state",
                "origin": "user",
                "tags": ["직장"],
                "source_ids": ["s1"],
            }
        ],
        "supersedes": {},
    }
)

_DEFAULTS = {
    "extract": _EXTRACTED,
    "need": json.dumps({"need": True}),
    "expand": json.dumps({"queries": ["직장"]}),
    "judge": json.dumps({"sufficient": True, "missing": ""}),
    "card": json.dumps({"tone_lines": ["직장 화제엔 조심스럽게"]}),
}


class FakeModel(BaseChatModel):
    """마커로 어느 노드가 불렀는지 알아내 스크립트된 답을 줌."""

    calls: list[str] = []
    fails_on: str = ""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("이 테스트는 ainvoke만 쓴다")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = " ".join(str(message.content) for message in messages)
        marker = next((name for needle, name in _MARKERS.items() if needle in text), "")
        assert marker, f"어느 프롬프트인지 못 찾았다: {text[:200]}"
        self.calls.append(marker)
        if marker == self.fails_on:
            raise RuntimeError(f"{marker} 실패")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=_DEFAULTS[marker]))])


def _one_turn() -> session_module.Session:
    session = session_module.empty()
    session["messages"] = [
        {"type": "human", "data": {"content": "회의마다 상사가 질책해서 힘들어"}},
        {"type": "ai", "data": {"content": "많이 힘드셨겠어요"}},
    ]
    return session


async def test_memory_is_built_on_a_session_far_below_the_compression_threshold(thread, monkeypatch) -> None:
    """압축은 수백 턴 뒤에야 걸림. 기억이 거기 묶여 있으면 평생 비어 있음."""
    monkeypatch.setattr(curator_graph, "_config", lambda: CURATOR_CONFIG)
    session = _one_turn()
    total_chars = sum(len(str(message["data"]["content"])) for message in session["messages"])

    result = await remember(session, FakeModel(calls=[]), thread)

    assert total_chars < 1000  # 어떤 압축 임계에도 한참 못 미치는데
    assert [node["subject"] for node in graph_store.nodes(thread)] == ["상사"]  # 노드는 생김(별칭 정규화 뒤)
    assert result["memory"]["tone_lines"] == ["직장 화제엔 조심스럽게"]


async def test_curator_is_skipped_when_nothing_was_extracted(thread, monkeypatch) -> None:
    monkeypatch.setattr(curator_graph, "_config", lambda: CURATOR_CONFIG)
    monkeypatch.setitem(_DEFAULTS, "extract", json.dumps({"nodes": [], "supersedes": {}}))
    model = FakeModel(calls=[])

    await remember(_one_turn(), model, thread)

    assert model.calls == ["extract"]  # 뽑힌 게 없으면 큐레이터를 안 부름
    assert graph_store.nodes(thread) == []


async def test_only_the_latest_turn_is_extracted(thread, monkeypatch) -> None:
    """지난 턴을 다시 넣으면 같은 사실이 턴마다 새 노드로 쌓임."""
    monkeypatch.setattr(curator_graph, "_config", lambda: CURATOR_CONFIG)
    session = _one_turn()
    session["messages"] += [
        {"type": "human", "data": {"content": "오늘은 발표가 무서워"}},
        {"type": "ai", "data": {"content": "떨리시겠어요"}},
    ]
    seen: list[str] = []

    class Recorder(FakeModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            joined = " ".join(str(message.content) for message in messages)
            if "장기기억 노드" in joined:
                seen.append(joined)
            return await super()._agenerate(messages, stop, run_manager, **kwargs)

    await remember(session, Recorder(calls=[]), thread)

    assert "발표가 무서워" in seen[0]
    assert "상사가 질책해서" not in seen[0]  # 지난 턴에서 이미 추출


async def test_compression_never_calls_the_extractor(thread, monkeypatch) -> None:
    """압축은 기억을 만들지도 지우지도 않음. 임계를 넘어도 추출을 부르지 않음."""
    monkeypatch.setattr(
        compress_graph,
        "_config",
        lambda: {"threshold_chars": 0, "recent_turns": 0, "keep_ratio_max": 1.0, "crisis_keywords": []},
    )
    graph_store.add(thread, [{"id": "kept", "thread_id": thread, "subject": "가", "object": "나", "status": "active"}])

    class Compressor(FakeModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            joined = " ".join(str(message.content) for message in messages)
            assert "장기기억 노드" not in joined, "압축이 추출을 부르면 안 된다"
            content = (
                json.dumps({"sentences": []}) if "채점 축" in joined else json.dumps({"summaries": [], "bridges": []})
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    result = await compress_run(_one_turn(), Compressor(calls=[]), thread)

    assert result["messages"]  # 압축은 정상 동작하고
    assert [node["id"] for node in graph_store.nodes(thread)] == ["kept"]  # 온톨로지 유지


async def test_previous_turn_question_is_passed_as_context(thread, monkeypatch) -> None:
    """AI 질문은 앞 턴, 답은 이번 턴이라 답만 보면 짧은 대답의 뜻을 알 수 없음."""
    monkeypatch.setattr(curator_graph, "_config", lambda: CURATOR_CONFIG)
    session = session_module.empty()
    session["messages"] = [
        {"type": "human", "data": {"content": "요즘 힘들어"}},
        {"type": "ai", "data": {"content": "어떻게 불러드릴까요?"}},
        {"type": "human", "data": {"content": "그냥 지원이요"}},
        {"type": "ai", "data": {"content": "네, 지원님"}},
    ]
    seen: list[str] = []

    class Recorder(FakeModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            joined = " ".join(str(message.content) for message in messages)
            if "장기기억 노드" in joined:
                seen.append(joined)
            return await super()._agenerate(messages, stop, run_manager, **kwargs)

    await remember(session, Recorder(calls=[]), thread)

    assert "어떻게 불러드릴까요?" in seen[0]  # 앞 턴 질문이 문맥으로 들어감
    assert "요즘 힘들어" not in seen[0]  # 그 앞 사용자 발화까지 끌고 오지는 않음
