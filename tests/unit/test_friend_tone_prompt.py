from __future__ import annotations

from app import guide
from app.graph.subgraphs.empathy.graph import CONFIG_FILE
from app.graph.subgraphs.review import graph as review_graph
from app import opening, prompt


def test_friend_tone_does_not_force_counselling_formulas() -> None:
    identity = prompt.identity_line()
    empathy = str(guide.load("app/graph/subgraphs/empathy/graph.py", CONFIG_FILE)["guide"])
    review = guide.load(
        "app/graph/subgraphs/review/graph.py", "healer_review.json"
    )["surface_checklist"]
    reason = str(
        guide.load("app/graph/subgraphs/reason/graph.py", "healer_reason.json")[
            "guide"
        ]
    )
    intent = guide.load(
        "app/graph/subgraphs/review/graph.py", "healer_review.json"
    )["intent_checklist"]

    assert "그랬구나" not in identity
    assert "진짜 힘들었겠다" not in identity
    assert "힘든 게 당연하다는 것만" not in empathy
    assert "직접 물은 말" in prompt.ANSWER_PROMPT
    assert "감정 요약" in prompt.ANSWER_PROMPT
    assert "사용자 호칭은 확인 전까지 모릅니다" in identity
    assert "사용자 호칭은 확인 전까지 모릅니다" in opening.OPENING_PROMPT
    assert "week_plus면 오랜만" in opening.OPENING_PROMPT
    assert "좋은 아침이야" in opening.OPENING_PROMPT
    assert "아침이네" in opening.OPENING_PROMPT
    assert "두 문장 구조" in opening.OPENING_PROMPT
    assert "여러 겹" in prompt.ANSWER_PROMPT
    assert "반응 하나" in empathy
    assert any("감정·몸 상태·미래 걱정" in item for item in review)
    assert "조건절로 되풀이" in empathy
    assert any("그 느낌" in item for item in review)
    assert "사건에 바로 반응" in prompt.ANSWER_PROMPT
    assert any("불안하고 막막" in item for item in review)
    assert "아, 그건 좀 급하네" in empathy
    assert any("할 수 있겠다" in item for item in review)
    assert "이미 하고 있는 일을 보고" in prompt.ANSWER_PROMPT
    assert "잘하고 있어" in reason
    assert any("요청하지 않은 체크리스트" in item for item in intent)


def test_surface_guard_catches_distanced_counselling_language() -> None:
    assert review_graph._friend_tone_notes(
        "회의에서 무능해 보일까 걱정될 수 있겠다."
    )
    assert review_graph._friend_tone_notes("지금도 그 느낌이 이어져?")
    assert review_graph._friend_tone_notes("아, 그건 좀 급하네.") == []
    assert review_graph._friend_tone_notes(
        "오, 다행이다. 안도되고 뿌듯하겠다."
    )


def test_intent_guard_catches_advice_after_a_progress_report() -> None:
    assert review_graph._unsolicited_advice_notes(
        "좋아. 이제 회의 목적부터 찾아봐.", "응, 역할 부분 찾았어."
    )
    assert review_graph._unsolicited_advice_notes(
        "좋아. 이제 회의 목적부터 찾아봐.", "뭐부터 해야 해?"
    ) == []
    assert review_graph._unsolicited_advice_notes(
        "응, 찾았네.", "응, 역할 부분 찾았어."
    ) == []
    assert review_graph._unsolicited_advice_notes(
        "좋아. 이제 핵심 하나만 잡자.", "말할 부분은 표시해뒀어."
    )
    assert review_graph._progress_fallback(
        "좋아. 이제 핵심 하나만 잡자.", "말할 부분은 표시해뒀어."
    ) == "좋아."
    assert review_graph._progress_fallback(
        "잘하고 있어. 이제 핵심 하나만 잡자.", "말할 부분은 표시해뒀어."
    ) == "응."
    assert review_graph._unsolicited_advice_notes(
        "좋아. 회의에서 말할 문장으로 준비해줄게.", "자료 핵심도 표시해뒀어."
    )
    assert review_graph._progress_fallback(
        "좋아. 회의에서 말할 문장으로 준비해줄게.", "자료 핵심도 표시해뒀어."
    ) == "좋아."
    assert review_graph._progress_fallback(
        "오, 다행이다. 안도되고 뿌듯하겠다.",
        "응, 회의는 끝났어. 자료 표시해둔 게 도움이 됐네.",
    ) == "오, 다행이다."
