"""큐레이터 서브그래프. 마커로 구분한 가짜 모델만 사용."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.session import store as session_module
from app.session.ontology import curator, graph_store
from app.session.ontology.curator import graph as curator_graph

BASE_NODE: dict = {
    "id": "n1",
    "thread_id": "t",
    "source_message_ids": [],
    "subject": "어머니",
    "predicate": "전화로 화를 냈다",
    "object": "지난달",
    "kind": "observation",
    "span": "event",
    "origin": "user",
    "occurred_at": None,
    "valid_from": "2026-01-01T00:00:00+00:00",
    "valid_to": None,
    "tags": ["가족"],
    "alias_of": None,
    "status": "active",
    "superseded_by": None,
    "disclosure": "quiet",
    "crisis": False,
    "sensitivity": False,
    "extraction_confidence": 0.8,
    "salience": 0.5,
}

CONFIG = {
    "curator_max_rounds": 3,
    "curator_candidate_limit": 5,
    "curator_recent_messages": 4,
    "memory_pack_ttl_seconds": 86400,
}

_MARKERS = {
    "배경 기억을 참고하는": "need",
    "별칭 사전 밖의 표현": "expand",
    "배경 후보 목록": "judge",
    "톤으로 말해야 하는지": "card",
}

_DEFAULTS = {
    "need": json.dumps({"need": True}),
    "expand": json.dumps({"queries": []}),
    "judge": json.dumps({"sufficient": True, "missing": ""}),
    "card": json.dumps({"tone_lines": []}),
}


def _marker(messages: list[BaseMessage]) -> str:
    text = " ".join(str(message.content) for message in messages)
    for needle, marker in _MARKERS.items():
        if needle in text:
            return marker
    raise AssertionError(f"어느 노드 프롬프트인지 못 찾았다: {text[:200]}")


class FakeModel(BaseChatModel):
    """마커로 어느 노드가 불렀는지 알아내 스크립트된 답을 줌."""

    script: dict[str, list[str]] = {}
    calls: list[str] = []

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
        marker = _marker(messages)
        self.calls.append(marker)
        queued = self.script.get(marker, [])
        seen_before = self.calls.count(marker) - 1
        content = queued[seen_before] if seen_before < len(queued) else (queued[-1] if queued else _DEFAULTS[marker])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


def _session(thread_id: str, *nodes: dict, text: str = "그냥 안녕") -> session_module.Session:
    """노드는 그래프에 존재함. 세션은 대화만 보관."""
    graph_store.add(thread_id, [{**node, "thread_id": thread_id} for node in nodes])
    base = session_module.empty()
    base["messages"] = [{"type": "human", "data": {"content": text}}]
    return base


async def test_need_false_skips_further_calls_and_leaves_memory_empty(thread, monkeypatch) -> None:
    monkeypatch.setattr(curator_graph, "_config", lambda: CONFIG)
    model = FakeModel(script={"need": [json.dumps({"need": False})]})

    result = await curator.curate(_session(thread), model, thread)

    assert result["memory"]["schema_version"] == 2
    assert result["memory"]["candidate_ids"] == []
    assert result["memory"]["tone_lines"] == []
    assert model.calls == ["need"]


async def test_expand_reaches_node_missed_by_alias_dictionary(thread, monkeypatch) -> None:
    """별칭 사전에는 '발표불안'이 없음. expand가 이 표현을 내야만 노드가 걸림."""
    monkeypatch.setattr(curator_graph, "_config", lambda: CONFIG)
    node = {**BASE_NODE, "id": "n1", "tags": ["발표불안"], "disclosure": "proactive"}
    model = FakeModel(
        script={
            "expand": [json.dumps({"queries": ["발표불안"]})],
            "judge": [json.dumps({"sufficient": True, "missing": ""})],
        }
    )

    result = await curator.curate(_session(thread, node, text="발표가 무서워"), model, thread)

    assert result["memory"]["candidate_ids"] == ["n1"]
    assert "candidates" not in result["memory"]
    assert "card" not in model.calls  # proactive 노드라 quiet 압축 대상이 아님


async def test_judge_requeries_until_round_cap_then_proceeds(thread, monkeypatch) -> None:
    monkeypatch.setattr(curator_graph, "_config", lambda: {**CONFIG, "curator_max_rounds": 2})
    model = FakeModel(
        script={
            "expand": [json.dumps({"queries": ["a"]}), json.dumps({"queries": ["b"]})],
            "judge": [json.dumps({"sufficient": False, "missing": "더 필요"})] * 5,
        }
    )

    result = await curator.curate(_session(thread), model, thread)

    assert model.calls.count("expand") == 2  # 상한 2를 넘겨 부르지 않음
    assert model.calls.count("judge") == 2
    assert result["memory"]["candidate_ids"] == []


async def test_card_tone_line_comes_only_from_llm_not_node_text(thread, monkeypatch) -> None:
    monkeypatch.setattr(curator_graph, "_config", lambda: CONFIG)
    node = {**BASE_NODE, "id": "n1", "tags": ["가족"], "disclosure": "quiet"}
    model = FakeModel(
        script={
            "expand": [json.dumps({"queries": ["가족"]})],
            "judge": [json.dumps({"sufficient": True, "missing": ""})],
            "card": [json.dumps({"tone_lines": ["가족 화제엔 조심스럽게"]})],
        }
    )

    result = await curator.curate(_session(thread, node, text="엄마 얘기 좀"), model, thread)

    tone_text = " ".join(result["memory"]["tone_lines"])
    assert result["memory"]["tone_lines"] == ["가족 화제엔 조심스럽게"]
    assert node["subject"] not in tone_text  # 원문 고유명사가 새지 않음
    assert node["predicate"] not in tone_text
