"""정체성 슬롯 저장·조회·질문 창."""

from __future__ import annotations

from app.session.ontology import graph_store, identity, schema


def _node(thread: str, **overrides: object) -> dict:
    raw = {
        "subject": "사용자",
        "predicate": "불린다",
        "object": "지원",
        "kind": "observation",
        "span": "state",
        "origin": "user",
        "slot": "name",
        "tags": ["호칭"],
        "extraction_confidence": 0.9,
    }
    raw.update(overrides)
    built = schema.build(raw, thread, ["m1"])
    assert built is not None
    return built


def test_schema_keeps_known_slot(thread) -> None:
    node = _node(thread, slot="name")
    assert node["slot"] == "name"


def test_schema_drops_unknown_slot(thread) -> None:
    node = _node(thread, slot="age")
    assert node["slot"] is None


def test_identity_query_user_origin_only(thread) -> None:
    user_node = _node(thread, slot="name", object="지원")
    inferred = _node(
        thread,
        subject="사용자",
        predicate="말투가",
        object="짧다",
        origin="inferred",
        slot="name",
    )
    graph_store.add(thread, [user_node, inferred])
    rows = graph_store.identity(thread)
    assert len(rows) == 1
    assert rows[0]["slot"] == "name"
    assert "지원" in rows[0]["value"]


def test_askable_empty_when_filled(thread) -> None:
    graph_store.add(thread, [_node(thread, slot="name")])
    askable = identity.askable_slots(
        thread,
        turn=10,
        identity_asks=0,
        turns_since_identity=None,
        crisis=False,
        intensity="중간",
    )
    assert "name" not in askable
    assert "day" in askable


def test_askable_blocked_on_crisis(thread) -> None:
    askable = identity.askable_slots(
        thread,
        turn=10,
        identity_asks=0,
        turns_since_identity=None,
        crisis=True,
        intensity=None,
    )
    assert askable == []


def test_askable_is_not_limited_by_numeric_turn_windows(thread) -> None:
    early = identity.askable_slots(
        thread, turn=1, identity_asks=0, turns_since_identity=None, crisis=False, intensity=None
    )
    much_later = identity.askable_slots(
        thread, turn=99, identity_asks=20, turns_since_identity=1, crisis=False, intensity=None
    )
    assert early
    assert much_later == early
