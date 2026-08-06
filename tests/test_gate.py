"""발화 게이팅. LLM을 타지 않음 — 전부 코드 판정임."""

from __future__ import annotations

from app import session as session_module
from app.session import store as session_store
from app.session.ontology import gate, graph_store
from app.session.ontology import store as ontology_store

CONFIG = {
    "disclosure_signals": {
        "remember": ["기억해"],
        "dated": ["다음\\s*주"],
        "stop": ["그만 말해"],
    },
    "salience_decay_per_day": 0.02,
    "tone_line_template": "{tag} 화제엔 조심스럽게",
}

BASE_NODE: dict = {
    "id": "n1",
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
}


def _session(thread_id: str, *nodes: dict) -> session_module.Session:
    """노드는 그래프에 넣고, 세션은 memory·opened_topics만 들고 있음."""
    graph_store.add(thread_id, [{**node, "thread_id": thread_id} for node in nodes])
    return session_module.empty()


# -- classify_disclosure (store.py) --------------------------------------


def test_inferred_origin_forces_quiet_even_with_promotion_signal() -> None:
    result = ontology_store.classify_disclosure("다음 주 면담 기억해줘", origin="inferred", config=CONFIG)
    assert result == "quiet"


def test_stop_signal_forces_quiet_even_with_promotion_signal() -> None:
    result = ontology_store.classify_disclosure("이제 그만 말해, 다음 주에 기억해", origin="user", config=CONFIG)
    assert result == "quiet"


def test_remember_signal_promotes_to_proactive() -> None:
    result = ontology_store.classify_disclosure("이거 기억해줘", origin="user", config=CONFIG)
    assert result == "proactive"


def test_dated_signal_promotes_to_proactive() -> None:
    result = ontology_store.classify_disclosure("다음 주에 면담 있어", origin="user", config=CONFIG)
    assert result == "proactive"


def test_no_signal_stays_quiet() -> None:
    result = ontology_store.classify_disclosure("오늘 날씨가 좋았어", origin="user", config=CONFIG)
    assert result == "quiet"


def test_decayed_salience_drops_with_age() -> None:
    from datetime import datetime, timezone

    node = {**BASE_NODE, "salience": 1.0, "valid_from": "2026-01-01T00:00:00+00:00"}
    now = datetime(2026, 1, 11, tzinfo=timezone.utc)  # 10일 경과

    decayed = ontology_store.decayed_salience(node, CONFIG, now=now)

    assert decayed < 1.0


# -- build_context (gate.py) ----------------------------------------------


def test_quiet_node_raw_text_never_enters_context(thread) -> None:
    session = _session(thread, {**BASE_NODE, "disclosure": "quiet"})

    context = gate.build_context(session, "오늘 그냥 산책했어", thread)

    assert "화를 낸다" not in context


def test_crisis_node_always_injected_ignoring_disclosure(thread) -> None:
    session = _session(thread, {**BASE_NODE, "disclosure": "quiet", "crisis": True})

    context = gate.build_context(session, "오늘 그냥 산책했어", thread)

    assert "화를 낸다" in context


def test_user_must_bring_up_topic_before_candidate_opens(thread) -> None:
    session = _session(thread, {**BASE_NODE, "disclosure": "quiet", "tags": ["가족"]})

    not_opened = gate.build_context(session, "오늘 그냥 산책했어", thread)
    assert "화를 낸다" not in not_opened

    opened = gate.build_context(session, "엄마가 또 화냈어", thread)  # 별칭 사전: 엄마→어머니
    assert "화를 낸다" in opened


def test_quiet_topic_closes_when_user_moves_on(thread) -> None:
    session = _session(thread, {**BASE_NODE, "disclosure": "quiet", "tags": ["가족"]})

    gate.build_context(session, "엄마가 또 화냈어", thread)  # 이번 턴에 공개
    later = gate.build_context(session, "오늘은 날씨 얘기만 할래", thread)

    assert "화를 낸다" not in later


def test_build_context_is_blank_string_when_nothing_matches(thread) -> None:
    assert gate.build_context(session_module.empty(), "아무 얘기나", thread) == ""


def test_tone_lines_stay_under_the_resident_ceiling(thread, monkeypatch) -> None:
    """노드가 쌓여도 배경이 끝없이 길어지면 안 됨."""
    monkeypatch.setattr(gate, "_config", lambda: {**CONFIG, "resident_limit": 2})
    many = [{**BASE_NODE, "id": f"n{index}", "tags": [f"태그{index}"]} for index in range(10)]

    context = gate.build_context(_session(thread, *many), "오늘 그냥 산책했어", thread)

    assert context.count("화제엔 조심스럽게") == 2


def _with_cached_background(thread_id: str, node: dict) -> session_module.Session:
    """큐레이터가 만들어둔 배경에는 노드 사본이 들어감. 그 사본은 그 뒤 사용자 조작을 모름."""
    session = _session(thread_id, node)
    session["memory"] = {"candidates": [dict(node)], "tone_lines": ["가족 화제엔 조심스럽게"], "proactive": []}
    session["opened_topics"] = ["어머니"]
    return session


def test_retracted_node_text_never_reaches_the_next_turn(thread) -> None:
    session = _with_cached_background(thread, {**BASE_NODE})
    graph_store.retract(thread, BASE_NODE["id"])

    context = gate.build_context(session, "어머니 얘기 좀 할까", thread)

    assert BASE_NODE["predicate"] not in context


def test_locked_node_is_not_injected_from_a_stale_copy(thread) -> None:
    """잠금은 '먼저 꺼내지 않는다'다. 꺼낸 적 없는 화제라야 억제가 드러남."""
    session = _with_cached_background(thread, {**BASE_NODE, "disclosure": "proactive"})
    session["opened_topics"] = []
    graph_store.quiet(thread, BASE_NODE["id"])

    context = gate.build_context(session, "오늘 그냥 산책했어", thread)

    assert BASE_NODE["predicate"] not in context


def test_v2_memory_pack_rehydrates_the_edited_live_node(thread) -> None:
    other = {
        **BASE_NODE,
        "id": "n2",
        "subject": "아버지",
        "predicate": "주말마다 전화한다",
        "object": "자주",
    }
    session = _session(thread, {**BASE_NODE}, other)
    session["memory"] = {
        "schema_version": 2,
        "candidate_ids": [BASE_NODE["id"]],
        "tone_lines": ["가족 화제엔 조심스럽게"],
        "generated_at": "2026-08-06T00:00:00+00:00",
        "expires_at": "2099-08-07T00:00:00+00:00",
    }
    graph_store.update(
        thread,
        BASE_NODE["id"],
        subject="어머니",
        predicate="요즘은 차분히 말한다",
        object_="가끔",
    )

    context = gate.build_context(session, "가족 얘기 좀 할까", thread)

    assert "화를 낸다" not in context
    assert "요즘은 차분히 말한다" in context
    assert "주말마다 전화한다" not in context


def test_expired_memory_pack_drops_cached_tone_lines(thread) -> None:
    session = _session(thread, {**BASE_NODE})
    session["memory"] = {
        "schema_version": 2,
        "candidate_ids": [BASE_NODE["id"]],
        "tone_lines": ["만료된 비밀 태그"],
        "generated_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2020-01-02T00:00:00+00:00",
    }

    context = gate.build_context(session, "오늘 그냥 산책했어", thread)

    assert "만료된 비밀 태그" not in context
    assert "가족 화제엔 조심스럽게" in context


# -- 열람/철회 --------------------------------------------------------------


def test_retract_then_get_memory_excludes_it(client) -> None:
    """기억은 세션이 아니라 사용자에 귀속. 온톨로지 키로 user_id 사용."""
    graph_store.add(client.user_id, [{**BASE_NODE, "id": "n1", "thread_id": client.user_id}])

    before = client.get("/api/memory").json()
    assert any(node["id"] == "n1" for node in before["nodes"])

    assert client.post("/api/memory/n1/retract").status_code == 200

    after = client.get("/api/memory").json()
    assert all(node["id"] != "n1" for node in after["nodes"])


def test_retract_returns_the_recomposed_graph_and_clears_cached_memory(
    client, session_id
) -> None:
    graph_store.add(
        client.user_id,
        [
            {**BASE_NODE, "id": "n1", "thread_id": client.user_id},
            {
                **BASE_NODE,
                "id": "n2",
                "thread_id": client.user_id,
                "subject": "사용자",
                "predicate": "즐겨 마신다",
                "object": "커피",
            },
        ],
    )
    stored = session_module.load(session_id)
    stored["memory"] = {"candidates": [{**BASE_NODE, "id": "n1"}], "tone_lines": []}
    session_module.save(session_id, stored)

    response = client.post("/api/memory/n1/retract")

    assert response.status_code == 200
    assert [node["id"] for node in response.json()["nodes"]] == ["n2"]
    assert response.json()["graph"]["entities"] == [
        {"id": "사용자", "label": "사용자"},
        {"id": "커피", "label": "커피"},
    ]
    assert session_module.load(session_id)["memory"] == {}


def test_retract_starts_semantic_recuration(client, monkeypatch) -> None:
    from app import main

    calls: list[str] = []

    async def recurate(user_id: str) -> None:
        calls.append(user_id)

    monkeypatch.setattr(main, "_recurate_latest_memory", recurate)
    graph_store.add(
        client.user_id,
        [{**BASE_NODE, "id": "n1", "thread_id": client.user_id}],
    )

    response = client.post("/api/memory/n1/retract")

    assert response.status_code == 200
    assert calls == [client.user_id]


def test_retract_unknown_node_id_is_404(client) -> None:
    assert client.post("/api/memory/없는아이디/retract").status_code == 404


def test_another_users_memory_is_not_reachable(client, thread) -> None:
    graph_store.add(thread, [{**BASE_NODE, "id": "n9", "thread_id": thread}])

    assert all(node["id"] != "n9" for node in client.get("/api/memory").json()["nodes"])
    assert client.post("/api/memory/n9/retract").status_code == 404
