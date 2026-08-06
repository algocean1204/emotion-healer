"""압축 하드룰 검증. 가짜 LLM 응답 dict만 넣고 LLM은 타지 않음."""

from app import session as session_module
from app.session.compress import rules


def test_to_sentences_splits_and_tags_turns() -> None:
    session = session_module.empty()
    session["messages"] = [
        {"type": "human", "data": {"content": "요즘 힘들어. 회사도 문제야"}},
        {"type": "ai", "data": {"content": "많이 힘드셨겠어요"}},
    ]

    sentences = rules.to_sentences(session)

    assert [sentence["id"] for sentence in sentences] == ["s1", "s2", "s3"]
    assert [sentence["turn_index"] for sentence in sentences] == [0, 0, 0]
    assert sentences[0]["text"] == "요즘 힘들어."


def test_crisis_sentence_survives_drop_verdict() -> None:
    sentences = [
        {"id": "s1", "message_index": 0, "turn_index": 0, "role": "human", "text": "죽고 싶다는 생각이 들어"},
    ]
    graded = [{"id": "s1", "scores": {"emotion": 3, "fact": 0, "open": 0}, "grade": "drop", "why": "LLM 실수"}]

    result = rules.enforce_crisis(sentences, graded, ["죽고 싶"])

    assert result[0]["grade"] == "keep"


def test_missing_id_filled_with_keep() -> None:
    sentences = [
        {"id": "s1", "message_index": 0, "turn_index": 0, "role": "human", "text": "문장 하나"},
        {"id": "s2", "message_index": 0, "turn_index": 0, "role": "human", "text": "문장 둘"},
    ]
    graded = [{"id": "s1", "scores": {"emotion": 1, "fact": 1, "open": 1}, "grade": "keep", "why": ""}]

    result = rules.fill_missing(sentences, graded)

    assert {record["id"] for record in result} == {"s1", "s2"}
    filled = next(record for record in result if record["id"] == "s2")
    assert filled["grade"] == "keep"


def test_keep_ratio_cap_is_enforced() -> None:
    graded = [
        {"id": f"s{index}", "scores": {"emotion": index % 4, "fact": 0, "open": 0}, "grade": "keep", "why": ""}
        for index in range(10)
    ]

    result = rules.cap_keep_ratio(graded, keep_ratio_max=0.4, protected_ids=set())

    assert len([record for record in result if record["grade"] == "keep"]) <= 4


def test_keep_ratio_cap_never_downgrades_protected() -> None:
    graded = [
        {"id": f"s{index}", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "keep", "why": ""}
        for index in range(5)
    ]

    result = rules.cap_keep_ratio(graded, keep_ratio_max=0.0, protected_ids={"s0"})

    kept_ids = {record["id"] for record in result if record["grade"] == "keep"}
    assert "s0" in kept_ids


def test_turn_pair_not_broken_by_full_user_drop() -> None:
    sentences = [
        {"id": "s1", "message_index": 0, "turn_index": 0, "role": "human", "text": "그때 있었던 일이야"},
        {"id": "s2", "message_index": 1, "turn_index": 0, "role": "ai", "text": "그러셨겠어요"},
    ]
    graded = [
        {"id": "s1", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "drop", "why": ""},
        {"id": "s2", "scores": {"emotion": 2, "fact": 1, "open": 1}, "grade": "keep", "why": ""},
    ]

    result = rules.enforce_turn_pairs(sentences, graded)

    user_grade = next(record for record in result if record["id"] == "s1")["grade"]
    assert user_grade != "drop"


def test_turn_pair_allows_full_drop_when_both_sides_drop() -> None:
    sentences = [
        {"id": "s1", "message_index": 0, "turn_index": 0, "role": "human", "text": "이건 필요없는 말"},
        {"id": "s2", "message_index": 1, "turn_index": 0, "role": "ai", "text": "그것도 필요없는 말"},
    ]
    graded = [
        {"id": "s1", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "drop", "why": ""},
        {"id": "s2", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "drop", "why": ""},
    ]

    result = rules.enforce_turn_pairs(sentences, graded)

    assert all(record["grade"] == "drop" for record in result)


def test_apply_grades_drops_and_bridges() -> None:
    session = session_module.empty()
    session["messages"] = [{"type": "human", "data": {"content": "필요없는 말. 남길 말"}}]
    sentences = [
        {"id": "s1", "message_index": 0, "turn_index": 0, "role": "human", "text": "필요없는 말."},
        {"id": "s2", "message_index": 0, "turn_index": 0, "role": "human", "text": "남길 말"},
    ]
    graded = [
        {"id": "s1", "scores": {"emotion": 0, "fact": 0, "open": 0}, "grade": "drop", "why": ""},
        {"id": "s2", "scores": {"emotion": 1, "fact": 1, "open": 1}, "grade": "keep", "why": ""},
    ]
    bridges = [{"after": "s1", "text": "(생략)"}]

    result = rules.apply_grades(session, sentences, graded, summaries=[], bridges=bridges)

    assert result["messages"][0]["data"]["content"] == "(생략) 남길 말"
    assert result["archive"] == session["messages"]
