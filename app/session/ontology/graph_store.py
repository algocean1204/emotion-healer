"""온톨로지 그래프 DB 접근. 트리플은 (:Statement) 노드로 펴고 인물만 (:Entity)로 뽑음.

관계에 얹지 않는 이유 세 가지. 관계를 관계로 가리킬 수 없어 개정 체인을 가변 길이로
못 타고, 술어를 관계 타입으로 쓰면 타입이 무한히 늘며, 관계 property에는 유니크 제약을
걸 수 없음. 판정 로직(정규화·승격·감쇠)은 store.py에 그대로 두고 여기서는 저장만 함.
"""

from __future__ import annotations

import os
from typing import Any

from neo4j import Driver, GraphDatabase, Session
from neo4j.api import BookmarkManager

# 컴포즈가 7687을 호스트로 열어둠. 백엔드는 호스트에서 도니 이게 기본임
DEFAULT_URI = "bolt://localhost:7687"

# Neo4j는 property에 null을 담지 못함. 읽을 때 없는 키는 이 값으로 되살림
NULLABLE_FIELDS = ("occurred_at", "valid_to", "alias_of", "superseded_by", "slot")
_driver: Driver | None = None
_bookmarks: BookmarkManager | None = None


def driver() -> Driver:
    global _driver, _bookmarks
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", DEFAULT_URI),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "")),
        )
        _bookmarks = GraphDatabase.bookmark_manager()
    return _driver


def db_session() -> Session:
    """세션마다 북마크를 이어 붙임. 안 그러면 방금 쓴 노드를 다음 세션이 못 봄 —
    추출 직후 노드 수 계산이 0이 되어 기억 생성이 누락됐던 문제."""
    driver()
    return _driver.session(bookmark_manager=_bookmarks)  # type: ignore[union-attr]


def close() -> None:
    global _driver, _bookmarks
    if _driver is not None:
        _driver.close()
        _driver = None
        _bookmarks = None


def _to_properties(node: dict) -> dict[str, Any]:
    """subject·object는 Entity로 빠지고, 값이 없는 키는 아예 안 넣음."""
    return {
        key: value
        for key, value in node.items()
        if key not in {"subject", "object"} and value is not None
    }


def _to_node(record: Any) -> dict:
    from app.session.ontology.schema import NODE_DEFAULTS

    # 기본값 위에 레코드를 얹음. 스키마에 필드를 추가해도 옛 노드 읽기가 안 죽음
    node = {**NODE_DEFAULTS, **dict(record["statement"])}
    node["subject"] = record["subject"]
    node["object"] = record["object"]
    for field in NULLABLE_FIELDS:
        node.setdefault(field, None)
    if node.get("tags") is None:
        node["tags"] = []
    return node


# 지운 노드는 아무 소비처도 안 쓰는데 영원히 쌓임. 매 턴 3~7회 전건을 끌어오는
# 경로라 거르는 자리가 여기여야 함 — 되살릴 일이 있는 쪽만 플래그로 받아 감
READ_QUERY = """
MATCH (s:Statement {thread_id: $thread_id})-[:SUBJECT]->(subject:Entity)
MATCH (s)-[:OBJECT]->(object:Entity)
WHERE $with_retracted OR s.status <> 'retracted'
RETURN s AS statement, subject.name AS subject, object.name AS object
ORDER BY s.valid_from
"""

COUNT_ACTIVE_QUERY = """
MATCH (s:Statement {thread_id: $thread_id})
WHERE s.status = 'active'
RETURN count(s) AS total
"""

# 정체성에 thread_id가 들어가야 함. id만 보면 남의 스레드 statement에 달라붙음.
# ON CREATE만 둬서 이미 있는 statement는 절대 덮이지 않음
WRITE_QUERY = """
UNWIND $nodes AS incoming
MERGE (s:Statement {thread_id: $thread_id, id: incoming.id})
  ON CREATE SET s += incoming.properties
MERGE (subject:Entity {thread_id: $thread_id, name: incoming.subject})
MERGE (object:Entity {thread_id: $thread_id, name: incoming.object})
MERGE (s)-[:SUBJECT]->(subject)
MERGE (s)-[:OBJECT]->(object)
"""

# 사용자가 누른 retracted를 뒤늦게 도착한 supersede가 되살리지 못하게 CASE를 씀
SUPERSEDE_QUERY = """
UNWIND $pairs AS pair
MATCH (old:Statement {id: pair.old, thread_id: $thread_id})
MATCH (new:Statement {id: pair.new, thread_id: $thread_id})
MERGE (old)-[:SUPERSEDED_BY]->(new)
SET old.superseded_by = pair.new,
    old.status = CASE old.status WHEN 'active' THEN 'superseded' ELSE old.status END
"""

PATCH_QUERY = """
MATCH (s:Statement {id: $node_id, thread_id: $thread_id})
SET s += $changes
RETURN s.id AS id
"""

UPDATE_QUERY = """
MATCH (s:Statement {id: $node_id, thread_id: $thread_id})
MATCH (s)-[old_subject:SUBJECT]->()
MATCH (s)-[old_object:OBJECT]->()
DELETE old_subject, old_object
SET s.predicate = $predicate
MERGE (subject:Entity {thread_id: $thread_id, name: $subject})
MERGE (object:Entity {thread_id: $thread_id, name: $object})
MERGE (s)-[:SUBJECT]->(subject)
MERGE (s)-[:OBJECT]->(object)
RETURN s.id AS id
"""

# 사용자 원문 정체성만. 추론(말투 등)은 slot 이 있어도 원문 주입 대상이 아님
# object 는 Statement 프로퍼티가 아닌 Entity — WRITE 가 SUBJECT/OBJECT 관계로 표현함
IDENTITY_QUERY = """
MATCH (s:Statement {thread_id: $thread_id})-[:OBJECT]->(object:Entity)
WHERE s.slot IS NOT NULL AND s.status = 'active' AND s.origin = 'user'
RETURN s.slot AS slot, s.predicate + ' ' + object.name AS value
ORDER BY s.valid_from
"""


def nodes(
    thread_id: str,
    with_retracted: bool = False,
    *,
    include_sensitive: bool = False,
) -> list[dict]:
    """기본적으로 민감 원문은 안 줌. crisis 는 안전 판단용이라 예외로 남김."""
    with db_session() as db:
        records = db.run(READ_QUERY, thread_id=thread_id, with_retracted=with_retracted)
        found = [_to_node(record) for record in records]
    if include_sensitive:
        return found
    return [
        node
        for node in found
        if not node.get("sensitivity") or node.get("crisis")
    ]


def has_active(thread_id: str) -> bool:
    """살아 있는 노드가 하나라도 있는지. 존재 여부만 보려고 전건을 끌어올 이유가 없음."""
    with db_session() as db:
        record = db.run(COUNT_ACTIVE_QUERY, thread_id=thread_id).single()
        return bool(record and record["total"])


def identity(thread_id: str) -> list[dict[str, str]]:
    """활성 사용자 정체성 슬롯. [{slot, value}, ...]. 슬롯당 여러 줄일 수 있음."""
    with db_session() as db:
        records = db.run(IDENTITY_QUERY, thread_id=thread_id)
        return [{"slot": str(record["slot"]), "value": str(record["value"])} for record in records]

def add(thread_id: str, new_nodes: list[dict], supersedes: dict[str, str] | None = None) -> None:
    """새 노드를 넣고 supersedes를 잇음. 삭제는 없음.

    둘을 한 트랜잭션에 묶음. 나누면 중간에 죽었을 때 옛 노드와 새 노드가 둘 다 active로
    남아 모순된 사실이 같은 프롬프트에 함께 들어감.
    """
    payload = [
        {"id": node["id"], "subject": node["subject"], "object": node["object"], "properties": _to_properties(node)}
        for node in new_nodes
    ]
    pairs = [{"old": old, "new": new} for old, new in (supersedes or {}).items()]
    if not payload and not pairs:
        return

    with db_session() as db:
        with db.begin_transaction() as tx:
            if payload:
                tx.run(WRITE_QUERY, thread_id=thread_id, nodes=payload)
            if pairs:
                tx.run(SUPERSEDE_QUERY, thread_id=thread_id, pairs=pairs)
            tx.commit()


def retract(thread_id: str, node_id: str) -> bool:
    """실제로 지우지 않음. status만 retracted로 바꿈."""
    return _patch(thread_id, node_id, {"status": "retracted"})


def quiet(thread_id: str, node_id: str) -> bool:
    """proactive를 quiet로 내림."""
    return _patch(thread_id, node_id, {"disclosure": "quiet"})


def update(
    thread_id: str,
    node_id: str,
    *,
    subject: str,
    predicate: str,
    object_: str,
) -> bool:
    """기억 문장을 고치고 Statement가 가리키는 Entity 관계를 다시 잇음."""
    with db_session() as db:
        record = db.run(
            UPDATE_QUERY,
            thread_id=thread_id,
            node_id=node_id,
            subject=subject,
            predicate=predicate,
            object=object_,
        ).single()
    return record is not None


def quiet_proactive(thread_id: str) -> int:
    """살아 있는 proactive 를 전부 quiet. 위기 노드는 남김.

    '그만 말해' 가 새 노드만 quiet 로 만들고 옛 proactive 는 그대로 두는 구멍을 막음.
    """
    changed = 0
    for node in nodes(thread_id, include_sensitive=True):
        if node.get("status") != "active":
            continue
        if node.get("disclosure") != "proactive":
            continue
        if node.get("crisis"):
            continue
        if quiet(thread_id, node["id"]):
            changed += 1
    return changed


def _patch(thread_id: str, node_id: str, changes: dict) -> bool:
    """thread_id를 패턴에 넣어 인가 검사. 한 DB에 모든 스레드가 모여 있음."""
    with db_session() as db:
        record = db.run(PATCH_QUERY, thread_id=thread_id, node_id=node_id, changes=changes).single()
    return record is not None
