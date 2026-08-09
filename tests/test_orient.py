"""대화 방향(orient) 정규화·배선. 네트워크 없음."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.graph import build_graph
from app.graph.subgraphs.orient import build as build_orient
from app.graph.subgraphs.orient import empty_arc, normalize
from tests.test_graph import FakeModel


def test_normalize_forces_empathy_when_both_without_handoff() -> None:
    arc = normalize({"mode": "both", "handoff": False, "phase": "공감중", "trajectory": "정체"})
    assert arc["mode"] == "empathy"
    assert arc["handoff"] is False


def test_normalize_keeps_both_with_handoff() -> None:
    arc = normalize(
        {
            "mode": "both",
            "handoff": True,
            "phase": "정리중",
            "trajectory": "나아짐",
            "user_stance": "조언요청",
            "commitments": ["숨 한 번"],
            "do_not": ["재촉"],
            "next_move": "짧게 방법 하나",
        }
    )
    assert arc["mode"] == "both"
    assert arc["handoff"] is True
    assert arc["commitments"] == ["숨 한 번"]


def test_normalize_clamps_unknown_enums() -> None:
    arc = normalize({"mode": "???", "phase": "외계", "trajectory": "??", "user_stance": "??"})
    assert arc["mode"] == "empathy"
    assert arc["phase"] == "열림"
    assert arc["trajectory"] == "불명"
    assert arc["user_stance"] == "불명"


def test_empty_arc_defaults() -> None:
    arc = empty_arc()
    assert arc["mode"] == "empathy"
    assert arc["commitments"] == []


async def test_orient_sets_route_from_mode() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"reason","trajectory":"정체","user_stance":"조언요청",'
                '"commitments":[],"do_not":["재촉"],"next_move":"선택지 둘","handoff":false}'
            ],
        }
    )
    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="이직 어떻게 해?")]})
    assert "orient" in model.calls
    assert out["route"] == "reason"
    assert out["arc"]["mode"] == "reason"
    assert out["arc"]["do_not"] == ["재촉"]
    assert "reason_write" in model.calls
    assert "empathy_write" not in model.calls


async def test_both_without_handoff_stays_on_empathy_only() -> None:
    """both 라도 handoff 없으면 방법 작성으로 안 넘어감."""
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"공감중","mode":"both","trajectory":"악화","user_stance":"조언거절",'
                '"commitments":[],"do_not":["해결책"],"next_move":"거절 인정","handoff":false}'
            ],
        }
    )
    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="그건 못 해")]})
    assert out["route"] == "empathy"  # normalize 가 both→empathy
    assert "empathy_write" in model.calls
    assert "reason_write" not in model.calls


async def test_both_with_handoff_runs_empathy_then_reason() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"정리중","mode":"both","trajectory":"나아짐","user_stance":"조언요청",'
                '"commitments":["어제 공감함"],"do_not":[],"next_move":"한 걸음","handoff":true}'
            ],
        }
    )
    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="그래서 어떻게 하면 돼")]})
    assert out["route"] == "both"
    assert out["arc"]["handoff"] is True
    assert model.calls.index("empathy_write") < model.calls.index("reason_write")


async def test_low_intensity_advice_request_skips_redundant_empathy_branch() -> None:
    model = FakeModel(
        script={
            "orient": [
                '{"phase":"실행중","mode":"both","trajectory":"나아짐","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"발표 순서 제안","handoff":true}'
            ]
        }
    )
    out = await build_orient(model).ainvoke(
        {
            "messages": [HumanMessage(content="발표 순서는 뭐부터 정하면 좋을까?")],
            "feeling": {"emotion": "안도감", "intensity": "낮음", "trigger": "", "hidden": ""},
        }
    )
    assert out["route"] == "reason"
    assert out["arc"]["handoff"] is False


async def test_worsening_advice_request_keeps_empathy_handoff() -> None:
    model = FakeModel(
        script={
            "orient": [
                '{"phase":"공감중","mode":"both","trajectory":"악화","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"불안 인정 후 방법","handoff":true}'
            ]
        }
    )
    out = await build_orient(model).ainvoke(
        {
            "messages": [HumanMessage(content="너무 불안한데 뭐부터 해야 해?")],
            "feeling": {"emotion": "불안", "intensity": "높음", "trigger": "", "hidden": ""},
        }
    )
    assert out["route"] == "both"
    assert out["arc"]["handoff"] is True


async def test_persona_merges_arc_do_not() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"공감중","mode":"empathy","trajectory":"정체","user_stance":"털어놓기",'
                '"commitments":[],"do_not":["성급한 해결"],"next_move":"감정 이름","handoff":false}'
            ],
            "persona": ['{"tone": ["짧게"], "view": "같이", "forbidden": ["재촉하기"]}'],
        }
    )
    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="힘들다")]})
    assert "성급한 해결" in out["persona"]["forbidden"]
    assert "재촉하기" in out["persona"]["forbidden"]


async def test_previous_arc_is_passed_into_orient_prompt() -> None:
    """세션에서 넘어온 previous_arc 가 sense 프롬프트에 실리는지 마커 경로로 간접 확인."""
    from app.graph.subgraphs.orient import prompt as orient_prompt

    messages = orient_prompt.sense_request(
        [HumanMessage(content="응")],
        feeling={"emotion": "지침", "intensity": "중간", "trigger": "", "hidden": ""},
        previous_arc={
            "phase": "공감중",
            "mode": "empathy",
            "trajectory": "정체",
            "user_stance": "털어놓기",
            "commitments": ["들어줌"],
            "do_not": [],
            "next_move": "더 듣기",
            "handoff": False,
        },
    )
    blob = " ".join(str(m.content) for m in messages)
    assert "previous_arc" in blob
    assert "공감중" in blob
    assert "대화 방향 판정" in blob or "국면" in blob
