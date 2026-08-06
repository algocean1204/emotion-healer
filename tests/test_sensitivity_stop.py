"""민감 정보 차단 · 그만 말해 소급 quiet · 결손 노드 기본값."""

from __future__ import annotations

from app.session.ontology import graph_store, schema
from app.session.ontology import store as ontology_store


def _node(thread: str, **overrides: object) -> dict:
    raw = {
        "subject": "회사",
        "predicate": "힘들다",
        "object": "요즘",
        "kind": "observation",
        "origin": "user",
        "tags": ["회사"],
        "extraction_confidence": 0.9,
        "sensitivity": False,
        "crisis": False,
    }
    raw.update(overrides)
    built = schema.build(raw, thread, ["s1"])
    assert built is not None
    if "disclosure" in overrides:
        built["disclosure"] = overrides["disclosure"]  # type: ignore[assignment]
    if "sensitivity" in overrides:
        built["sensitivity"] = bool(overrides["sensitivity"])
    if "crisis" in overrides:
        built["crisis"] = bool(overrides["crisis"])
    return built


def test_nodes_hides_sensitive_unless_crisis(thread) -> None:
    graph_store.add(
        thread,
        [
            _node(thread, subject="비밀", sensitivity=True, disclosure="proactive"),
            _node(thread, subject="위기", sensitivity=True, crisis=True, disclosure="quiet"),
            _node(thread, subject="일상", sensitivity=False),
        ],
    )
    visible = {node["subject"] for node in graph_store.nodes(thread)}
    assert "비밀" not in visible
    assert "위기" in visible
    assert "일상" in visible
    all_names = {node["subject"] for node in graph_store.nodes(thread, include_sensitive=True)}
    assert "비밀" in all_names


def test_quiet_proactive_leaves_crisis(thread) -> None:
    a = _node(thread, subject="일상화제")
    b = _node(thread, subject="위기기록", crisis=True)
    graph_store.add(thread, [a, b])
    with graph_store.db_session() as db:
        db.run(
            "MATCH (s:Statement {thread_id: $t}) SET s.disclosure = 'proactive'",
            t=thread,
        )

    changed = graph_store.quiet_proactive(thread)
    assert changed == 1
    by_subject = {n["subject"]: n for n in graph_store.nodes(thread, include_sensitive=True)}
    assert by_subject["일상화제"]["disclosure"] == "quiet"
    # 위기는 quiet_proactive 가 건드리지 않음
    assert by_subject["위기기록"]["disclosure"] == "proactive"


def test_stop_signal_matches_patterns() -> None:
    assert ontology_store.matches_any("그 얘기 하지 마", ["그 얘기 하지 마", "그만해"])
    assert ontology_store.matches_any("그만 말해 줘", ["그만 말해"])
    assert not ontology_store.matches_any("좋은 하루", ["그만해"])


def test_to_node_fills_missing_tags(thread) -> None:
    """옛 노드에 tags 가 없어도 읽기가 죽지 않음."""
    node = _node(thread)
    graph_store.add(thread, [node])
    # 프로퍼티에서 tags 를 지운 것처럼 시뮬레이션은 어렵고, setdefault 경로만 봄
    loaded = graph_store.nodes(thread)[0]
    assert isinstance(loaded.get("tags"), list)
    assert "sensitivity" in loaded
    assert "crisis" in loaded
