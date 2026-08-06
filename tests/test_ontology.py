"""온톨로지 그래프 저장. 판정 함수는 DB를 쓰지 않고 저장 테스트만 DB 사용."""

from __future__ import annotations

from app.session.ontology import graph_store, retrieve
from app.session.ontology import store as ontology_store

BASE_NODE: dict = {
    "id": "base",
    "thread_id": "t",
    "source_message_ids": [],
    "subject": "어머니",
    "predicate": "화를 낸다",
    "object": "자주",
    "kind": "observation",
    "span": "state",
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
    "slot": None,
}


def test_supersede_marks_old_node_but_keeps_it(thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread}])

    graph_store.add(thread, [{**BASE_NODE, "id": "n2", "thread_id": thread, "object": "가끔"}], {"n1": "n2"})

    by_id = {node["id"]: node for node in graph_store.nodes(thread)}
    assert len(by_id) == 2  # 원본이 지워지지 않음
    assert by_id["n1"]["status"] == "superseded"
    assert by_id["n1"]["superseded_by"] == "n2"
    assert by_id["n2"]["status"] == "active"


def test_supersede_does_not_revive_a_node_the_user_deleted(thread) -> None:
    """사용자가 누른 지움이 뒤늦게 도착한 승계보다 우선함."""
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread}])
    graph_store.retract(thread, "n1")

    graph_store.add(thread, [{**BASE_NODE, "id": "n2", "thread_id": thread}], {"n1": "n2"})

    by_id = {node["id"]: node for node in graph_store.nodes(thread, with_retracted=True)}
    assert by_id["n1"]["status"] == "retracted"
    # 기본 조회에는 안 나옴. 소비처가 하나도 안 쓰는 걸 매 턴 전건으로 끌어올 이유가 없음
    assert "n1" not in {node["id"] for node in graph_store.nodes(thread)}


def test_existing_node_is_never_overwritten(thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread, "salience": 0.9}])

    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread, "salience": 0.1}])

    assert graph_store.nodes(thread)[0]["salience"] == 0.9


def test_alias_normalizes_subject_into_one_entity(thread) -> None:
    aliases = {"엄마": "어머니"}
    node_a = ontology_store.normalize({**BASE_NODE, "id": "n1", "thread_id": thread, "subject": "엄마"}, aliases)
    node_b = ontology_store.normalize({**BASE_NODE, "id": "n2", "thread_id": thread, "subject": "어머니"}, aliases)

    graph_store.add(thread, [node_a, node_b])

    stored = graph_store.nodes(thread)
    assert {node["subject"] for node in stored} == {"어머니"}
    assert {node["alias_of"] for node in stored} == {"엄마", None}
    # 두 statement가 같은 Entity 하나를 공유해야 "이 사람 얽힌 것 전부"가 한 홉임
    with graph_store.db_session() as db:
        found = db.run(
            "MATCH (e:Entity {thread_id: $t, name: '어머니'}) RETURN count(e) AS n", t=thread
        ).single()
    assert found is not None and found["n"] == 1


def test_another_thread_cannot_touch_these_nodes(thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread}])

    assert graph_store.retract("남의-스레드", "n1") is False
    assert graph_store.nodes(thread)[0]["status"] == "active"


def test_update_reconnects_subject_and_object_entities(thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread}])

    assert graph_store.update(
        thread,
        "n1",
        subject="사용자",
        predicate="좋아한다",
        object_="저녁 산책",
    )

    stored = graph_store.nodes(thread)[0]
    assert (stored["subject"], stored["predicate"], stored["object"]) == (
        "사용자",
        "좋아한다",
        "저녁 산책",
    )


def test_another_thread_cannot_update_a_node(thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n1", "thread_id": thread}])

    assert not graph_store.update(
        "남의-스레드",
        "n1",
        subject="사용자",
        predicate="좋아한다",
        object_="저녁 산책",
    )
    assert graph_store.nodes(thread)[0]["predicate"] == BASE_NODE["predicate"]


def test_cap_resident_never_evicts_crisis_nodes() -> None:
    crisis_nodes = [{**BASE_NODE, "id": f"c{i}", "crisis": True, "salience": 0.1} for i in range(4)]
    normal_nodes = [{**BASE_NODE, "id": f"o{i}", "crisis": False, "salience": 0.9} for i in range(4)]

    selected = retrieve.cap_resident(crisis_nodes + normal_nodes, limit=2)

    selected_ids = {node["id"] for node in selected}
    assert {node["id"] for node in crisis_nodes} <= selected_ids
