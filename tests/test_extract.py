"""온톨로지에는 사용자가 말한 사실만 남김."""

from __future__ import annotations

import json
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.session.ontology import graph_store
from app.session.ontology.extract import extract
from app.session.ontology import gate
from app import session


class _ExtractorModel:
    async def ainvoke(self, _messages):
        return AIMessage(
            content=json.dumps(
                {
                    "nodes": [
                        {
                            "subject": "사용자",
                            "predicate": "일찍 움직인다",
                            "object": "아침에",
                            "origin": "inferred",
                            "source_ids": ["u1"],
                        },
                        {
                            "subject": "사용자",
                            "predicate": "일한다",
                            "object": "회사에서",
                            "origin": "user",
                            "source_ids": ["a1"],
                        },
                        {
                            "subject": "사용자",
                            "predicate": "학교에 다닌다",
                            "object": "요즘",
                            "origin": "user",
                            "source_ids": ["u1"],
                        },
                    ],
                    "supersedes": {},
                },
                ensure_ascii=False,
            )
        )


async def test_extract_keeps_only_user_backed_nodes(monkeypatch) -> None:
    saved: list[dict] = []
    monkeypatch.setattr(graph_store, "nodes", lambda _thread_id: [])
    monkeypatch.setattr(
        graph_store,
        "add",
        lambda _thread_id, nodes, _supersedes: saved.extend(nodes),
    )

    await extract(
        "jiwon",
        [
            {"id": "u1", "role": "human", "text": "요즘 학교에 다녀"},
            {"id": "a1", "role": "ai", "text": "아침형이구나"},
        ],
        cast(BaseChatModel, _ExtractorModel()),
    )

    assert [(node["predicate"], node["object"]) for node in saved] == [("학교에 다닌다", "요즘")]


def test_gate_ignores_a_legacy_inferred_node(monkeypatch) -> None:
    monkeypatch.setattr(
        gate.graph_store,
        "nodes",
        lambda _thread_id: [
            {
                "id": "n1",
                "status": "active",
                "origin": "inferred",
                "subject": "사용자",
                "predicate": "아침형이다",
                "object": "추정",
                "tags": ["생활"],
                "disclosure": "proactive",
                "sensitivity": False,
                "crisis": False,
            }
        ],
    )
    monkeypatch.setattr(gate, "identity_lines", lambda _thread_id: [])
    monkeypatch.setattr(gate, "_config", lambda: {"resident_limit": 5})

    context = gate.build_context(session.empty("jiwon", "jiwon-1"), "오늘 왔어", "jiwon")

    assert "아침형" not in context
