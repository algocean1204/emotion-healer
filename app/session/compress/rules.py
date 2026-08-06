"""LLM이 아닌 코드 몫. 문장 분해, 하드룰, 검증, 원문 재구성."""

from __future__ import annotations

import re

from app import crisis
from app.session.store import Session

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|\n+")

GRADE_ORDER = ("keep", "summarize", "drop")


def split_sentences(text: str) -> list[str]:
    """문장 단위로 쪼갬. 빈 조각은 버림."""
    pieces = [piece.strip() for piece in SENTENCE_BOUNDARY.split(text)]
    return [piece for piece in pieces if piece]


def to_sentences(session: Session) -> list[dict]:
    """세션 메시지 전체를 문장으로 쪼개고 s1, s2… id를 붙임."""
    sentences: list[dict] = []
    turn_index = -1
    for message_index, message in enumerate(session["messages"]):
        role = message.get("type", "")
        if role == "human":
            turn_index += 1
        turn_index = max(turn_index, 0)
        content = str(message.get("data", {}).get("content", ""))
        for piece in split_sentences(content):
            sentences.append(
                {
                    "id": f"s{len(sentences) + 1}",
                    "message_index": message_index,
                    "turn_index": turn_index,
                    "role": role,
                    "text": piece,
                }
            )
    return sentences


def recent_ids(sentences: list[dict], recent_turns: int) -> set[str]:
    """최근 N턴에 속한 문장 id. 채점 없이 원문 고정 대상임."""
    if recent_turns <= 0:
        return set()
    turn_indices = sorted({sentence["turn_index"] for sentence in sentences})
    recent_turn_indices = set(turn_indices[-recent_turns:])
    return {sentence["id"] for sentence in sentences if sentence["turn_index"] in recent_turn_indices}


def crisis_ids(sentences: list[dict], crisis_keywords: list[str]) -> set[str]:
    """위기 키워드가 든 문장 id."""
    return {
        sentence["id"]
        for sentence in sentences
        if crisis.has_signal(sentence["text"], crisis_keywords)
    }


def scoring_candidates(sentences: list[dict], recent_turns: int) -> list[dict]:
    """최근 턴을 뺀 나머지만 LLM 채점에 보냄."""
    excluded = recent_ids(sentences, recent_turns)
    return [sentence for sentence in sentences if sentence["id"] not in excluded]


def fixed_keep_grades(sentences: list[dict], recent_turns: int) -> list[dict]:
    """최근 턴 문장은 채점 없이 유지 등급을 받음."""
    excluded = recent_ids(sentences, recent_turns)
    return [
        {"id": sentence["id"], "grade": "keep", "why": "최근 턴, 원문 고정"}
        for sentence in sentences
        if sentence["id"] in excluded
    ]


def fill_missing(sentences: list[dict], graded: list[dict]) -> list[dict]:
    """전 문장 id 커버를 검증하고, 빠진 건 유지로 메움. 재시도는 없음."""
    covered = {record["id"] for record in graded}
    missing = [
        {"id": sentence["id"], "grade": "keep", "why": "누락, 유지로 메움"}
        for sentence in sentences
        if sentence["id"] not in covered
    ]
    return graded + missing


def enforce_crisis(sentences: list[dict], graded: list[dict], crisis_keywords: list[str]) -> list[dict]:
    """위기 신호 문장은 LLM이 drop을 내도 유지로 뒤집음."""
    protected = crisis_ids(sentences, crisis_keywords)
    return [
        {**record, "grade": "keep", "why": "위기 신호, 강제 유지"}
        if record["id"] in protected and record["grade"] != "keep"
        else record
        for record in graded
    ]


def _total_score(record: dict) -> int:
    scores = record.get("scores", {})
    return sum(scores.get(axis, 0) for axis in ("emotion", "fact", "open"))


def cap_keep_ratio(graded: list[dict], keep_ratio_max: float, protected_ids: set[str]) -> list[dict]:
    """유지 등급 비율이 상한을 넘으면 점수 낮은 것부터 요약으로 내림. 보호 대상은 안 건드림."""
    downgradable = [record for record in graded if record["grade"] == "keep" and record["id"] not in protected_ids]
    keep_count = len([record for record in graded if record["grade"] == "keep"])
    limit = int(len(graded) * keep_ratio_max)
    excess = keep_count - limit
    if excess <= 0 or not downgradable:
        return graded
    downgrade_ids = {record["id"] for record in sorted(downgradable, key=_total_score)[:excess]}
    return [
        {**record, "grade": "summarize", "why": (record.get("why", "") + " · 유지 비율 상한").strip(" ·")}
        if record["id"] in downgrade_ids
        else record
        for record in graded
    ]


def enforce_turn_pairs(sentences: list[dict], graded: list[dict]) -> list[dict]:
    """user 문장을 전부 버려 assistant 응답만 남는 걸 막음. 그런 턴은 user 쪽을 요약으로 완화함."""
    grade_by_id = {record["id"]: record["grade"] for record in graded}
    turns: dict[int, dict[str, list[str]]] = {}
    for sentence in sentences:
        turn = turns.setdefault(sentence["turn_index"], {"human": [], "ai": []})
        if sentence["role"] in turn:
            turn[sentence["role"]].append(sentence["id"])

    softened: set[str] = set()
    for turn in turns.values():
        human_ids, ai_ids = turn["human"], turn["ai"]
        if not human_ids or not ai_ids:
            continue
        human_all_dropped = all(grade_by_id.get(sentence_id) == "drop" for sentence_id in human_ids)
        ai_all_dropped = all(grade_by_id.get(sentence_id) == "drop" for sentence_id in ai_ids)
        if human_all_dropped and not ai_all_dropped:
            softened.update(human_ids)

    return [
        {**record, "grade": "summarize", "why": (record.get("why", "") + " · 답이 고아 되는 것을 막음").strip(" ·")}
        if record["id"] in softened
        else record
        for record in graded
    ]


def covers_all(sentences: list[dict], graded: list[dict]) -> bool:
    """전 문장 id가 등급을 받았는지 검사함."""
    return {sentence["id"] for sentence in sentences} <= {record["id"] for record in graded}


def grades_valid(graded: list[dict]) -> bool:
    """등급 값이 정해진 세 가지 안에 있는지 검사함."""
    return all(record.get("grade") in GRADE_ORDER for record in graded)


def crisis_kept(sentences: list[dict], graded: list[dict], crisis_keywords: list[str]) -> bool:
    """위기 신호 문장이 실제로 유지 등급인지 검사함."""
    protected = crisis_ids(sentences, crisis_keywords)
    grade_by_id = {record["id"]: record["grade"] for record in graded}
    return all(grade_by_id.get(sentence_id) == "keep" for sentence_id in protected)


def apply_grades(
    session: Session,
    sentences: list[dict],
    graded: list[dict],
    summaries: list[dict],
    bridges: list[dict],
) -> Session:
    """등급·요약·브리지를 원문에 적용해 줄어든 세션을 만듦. 원본은 archive로 옮김."""
    grade_by_id = {record["id"]: record["grade"] for record in graded}
    score_by_id = {record["id"]: _total_score(record) for record in graded}
    text_by_id = {sentence["id"]: sentence["text"] for sentence in sentences}

    summary_by_id: dict[str, dict] = {}
    for summary in summaries:
        for sentence_id in summary.get("replaces", []):
            summary_by_id[sentence_id] = summary

    bridges_by_anchor: dict[str, list[str]] = {}
    for bridge in bridges:
        bridges_by_anchor.setdefault(bridge.get("after", ""), []).append(bridge.get("text", ""))

    pieces_by_message: dict[int, list[str]] = {}
    emitted_summaries: set[int] = set()
    for sentence in sentences:
        pieces = pieces_by_message.setdefault(sentence["message_index"], [])
        sentence_id = sentence["id"]
        grade = grade_by_id.get(sentence_id, "keep")
        summary = summary_by_id.get(sentence_id)

        if summary is not None:
            if id(summary) not in emitted_summaries:
                emitted_summaries.add(id(summary))
                replaced_ids = summary.get("replaces", [sentence_id])
                core_id = max(replaced_ids, key=lambda i: score_by_id.get(i, 0))
                core_text = text_by_id.get(core_id, "")
                pieces.append(f"{summary.get('text', '')} ({core_text})".strip())
        elif grade != "drop":
            pieces.append(sentence["text"])

        for bridge_text in bridges_by_anchor.get(sentence_id, []):
            pieces.append(bridge_text)

    new_messages = []
    for message_index, message in enumerate(session["messages"]):
        data = dict(message.get("data", {}))
        data["content"] = " ".join(piece for piece in pieces_by_message.get(message_index, []) if piece)
        new_messages.append({**message, "data": data})

    # 등급이 다 keep 으로 떨어지면 결과가 원본과 같음. 그때도 archive 에 붙이면
    # 세션 파일이 매 턴 전체 크기만큼 커짐 — 줄인 게 있을 때만 원본을 넘김
    if new_messages == session["messages"]:
        return session

    return {
        **session,
        "messages": new_messages,
        "archive": [*session.get("archive", []), *session["messages"]],
    }
