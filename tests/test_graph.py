"""그래프 배선 스모크 테스트. 네트워크도 Codex도 안 탐."""

from __future__ import annotations

from typing import Any, Optional, cast

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.graph import build_graph
from app.graph.persona import graph as persona_graph
from app.graph.state import State
from app.graph.subgraphs.review import graph as review_graph

# 각 노드 프롬프트의 고유 문구로 어느 노드가 호출했는지 구분함
_MARKERS = {
    "되물을지와 감정 상태를 함께 판단하세요": "prepare",
    "되물을지 판정하세요": "decide",
    "부담 없이 이어 묻는 한 줄": "situation",
    "생활의 한 조각을 대화 흐름 속에서 자연스럽게 알아보는": "identity",
    "감정 상태를 분석하세요": "analyze",
    "어떤 마음이 가장 큰지": "question",
    "대화 방향 판정자": "orient",
    "말투와 관점을 정하고": "persona",
    "지금은 공감이 필요한 상황입니다": "empathy_write",
    "지금은 방법이 필요한 상황입니다": "reason_write",
    "문제가 없으면 초안을 한 글자도 바꾸지 마세요": "finalize",
}

_DEFAULTS = {
    "prepare": (
        '{"ask":"skip","feeling":{"emotion":"소진","intensity":"높음",'
        '"trigger":"회사","hidden":""}}'
    ),
    "decide": "skip",
    "situation": "언제부터 그러셨어요?",
    "analyze": '{"emotion": "소진", "intensity": "높음", "trigger": "회사", "hidden": ""}',
    "question": "어떤 마음이 가장 커요?",
    "orient": (
        '{"phase":"공감중","mode":"empathy","trajectory":"불명","user_stance":"털어놓기",'
        '"commitments":[],"do_not":[],"next_move":"감정 먼저","handoff":false}'
    ),
    "persona": '{"tone": ["짧게"], "view": "감정 먼저", "forbidden": []}',
    "empathy_write": "들으니 많이 힘드셨겠어요.",
    "reason_write": "오늘 해볼 수 있는 건 이거예요.",
    "finalize": "들으니 많이 힘드셨겠어요.",
}


def _marker(messages: list[BaseMessage]) -> str:
    text = " ".join(str(message.content) for message in messages)
    for needle, marker in _MARKERS.items():
        if needle in text:
            return marker
    raise AssertionError(f"어느 노드 프롬프트인지 못 찾았다: {text[:200]}")


class FakeModel(BaseChatModel):
    """실제 LLM 대신 마커로 어느 노드가 불렀는지 알아내 스크립트된 답을 줌."""

    script: dict[str, list[str]] = {}
    calls: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("이 테스트는 ainvoke만 쓴다")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        marker = _marker(messages)
        self.calls.append(marker)
        queued = self.script.get(marker, [])
        seen_before = self.calls.count(marker) - 1
        if seen_before < len(queued):
            content = queued[seen_before]
        elif queued:
            content = queued[-1]
        else:
            content = _DEFAULTS[marker]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


async def test_asked_true_skips_reask() -> None:
    model = FakeModel()

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="그리고 회사도 문제야")], "asked": True}
    )

    assert "decide" not in model.calls  # asked=True면 LLM 판정 없이 바로 skip
    assert out["asked"] is False
    assert out["messages"][-1].content == "들으니 많이 힘드셨겠어요."


async def test_answer_preparation_combines_question_decision_and_feeling() -> None:
    model = FakeModel(
        script={
            "prepare": [
                '{"ask":"skip","feeling":{"emotion":"긴장","intensity":"중간",'
                '"trigger":"회의","hidden":""}}'
            ]
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="내일 회의가 좀 신경 쓰여.")]}
    )

    assert model.calls.count("prepare") == 1
    assert "decide" not in model.calls
    assert "analyze" not in model.calls
    assert out["feeling"]["emotion"] == "긴장"


async def test_emotion_question_reuses_the_bundled_feeling() -> None:
    model = FakeModel(
        script={
            "prepare": [
                '{"ask":"emotion","feeling":{"emotion":"답답함","intensity":"중간",'
                '"trigger":"회사","hidden":""}}'
            ],
            "question": ["답답한 게 제일 커?"],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="회사 때문에 좀 복잡해.")]}
    )

    assert model.calls.count("prepare") == 1
    assert model.calls.count("question") == 1
    assert "analyze" not in model.calls
    assert out["messages"][-1].content == "답답한 게 제일 커?"
    assert out["asked"] is True


async def test_prepare_question_ends_turn() -> None:
    model = FakeModel(
        script={
            "prepare": [
                '{"ask":"situation","feeling":{"emotion":"힘듦","intensity":"중간",'
                '"trigger":"","hidden":""}}'
            ]
        }
    )

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="힘들어")]})

    assert out["asked"] is True
    assert out["messages"][-1].content == "언제부터 그러셨어요?"
    # orient·persona·write 진입 전 질문 하나로 턴 종료
    assert "orient" not in model.calls
    assert "empathy_write" not in model.calls


async def test_identity_question_ends_turn_without_a_profile_form() -> None:
    model = FakeModel(
        script={
            "prepare": [
                '{"ask":"identity","feeling":{"emotion":"혼란","intensity":"중간",'
                '"trigger":"","hidden":""}}'
            ],
            "identity": ["요즘 일이나 학교 쪽으로 더 바쁜 편이야?"],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {
            "messages": [HumanMessage(content="오늘 좀 정신없었어")],
            "askable_slots": ["day"],
            "identity_boundaries": ["가족 얘기는 하지 마"],
        }
    )

    assert out["asked"] is True
    assert out["messages"][-1].content == "요즘 일이나 학교 쪽으로 더 바쁜 편이야?"
    assert "orient" not in model.calls


async def test_long_message_keeps_the_question_agent_decision() -> None:
    """길이만으로 질문을 막지 않음. 자연스러움 판단은 모델의 문맥 판정에 맡김."""
    model = FakeModel(
        script={
            "prepare": [
                '{"ask":"situation","feeling":{"emotion":"억울함","intensity":"높음",'
                '"trigger":"회의","hidden":""}}'
            ]
        }
    )
    long = "어제 회의에서 팀장이 내 탓을 해서 너무 억울하고 지금도 잠이 안 와요."

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content=long)]})

    assert out["asked"] is True
    assert out["messages"][-1].content == "언제부터 그러셨어요?"


async def test_both_runs_empathy_then_reason() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"정리중","mode":"both","trajectory":"정체","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"짧게","handoff":true}'
            ],
            "finalize": ["들으니 많이 힘드셨겠어요.", "오늘 해볼 수 있는 건 이거예요."],
        }
    )

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="팀장이 또 내 탓을 했어")]})

    assert out["route"] == "both"
    assert model.calls.index("empathy_write") < model.calls.index("reason_write")
    assert model.calls.count("finalize") == 2
    assert out["messages"][-1].content == "오늘 해볼 수 있는 건 이거예요."
    assert out["asked"] is False


async def test_answer_turn_refreshes_feeling() -> None:
    """되묻지 않는 턴에도 감정을 다시 재야 route·persona가 이전 턴 값을 안 읽음."""
    model = FakeModel()

    out = await build_graph(llm=model).ainvoke(
        {
            "messages": [HumanMessage(content="회의 끝나면 진이 빠져")],
            "feeling": {"emotion": "옛날값", "intensity": "", "trigger": "", "hidden": ""},
        }
    )

    assert "prepare" in model.calls
    assert "analyze" not in model.calls
    assert out["feeling"]["emotion"] == "소진"


async def test_persona_sees_the_route_it_must_not_contradict() -> None:
    """persona가 분기를 모르면 `조언하기` 금지가 reason 초안을 정의상 떨어뜨림."""
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"reason","trajectory":"정체","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"선택","handoff":false}'
            ],
            "persona": ['{"tone": ["짧게"], "view": "방법", "forbidden": ["조언하기", "재촉하기"]}'],
        }
    )

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="이직할까 말까")]})

    assert model.calls.index("orient") < model.calls.index("persona")
    assert out["persona"]["forbidden"] == ["재촉하기"]


async def test_persona_reuses_the_previous_tone_during_its_four_turn_lease() -> None:
    model = FakeModel()
    node = persona_graph.build(model)
    previous = {"tone": ["차분하게"], "view": "옛 흐름", "forbidden": ["재촉하기"]}
    arc = {
        "phase": "공감중",
        "mode": "empathy",
        "trajectory": "정체",
        "user_stance": "털어놓기",
        "commitments": [],
        "do_not": ["해결책 밀어붙이기"],
        "next_move": "말을 더 듣기",
        "handoff": False,
    }

    out = await node(cast(State, {
        "messages": [HumanMessage(content="아직 좀 답답해")],
        "persona": previous,
        "persona_turn": 1,
        "turn": 4,
        "previous_arc": arc,
        "arc": arc,
        "route": "empathy",
    }))

    assert "persona" not in model.calls
    assert out == {
        "persona": {
            "tone": ["차분하게"],
            "view": "말을 더 듣기",
            "forbidden": ["해결책 밀어붙이기", "재촉하기"],
        },
        "persona_turn": 1,
    }


async def test_persona_refreshes_after_four_leased_turns() -> None:
    model = FakeModel()
    node = persona_graph.build(model)
    arc = {
        "phase": "공감중",
        "mode": "empathy",
        "trajectory": "정체",
        "user_stance": "털어놓기",
        "commitments": [],
        "do_not": [],
        "next_move": "말을 더 듣기",
        "handoff": False,
    }

    out = await node(cast(State, {
        "messages": [HumanMessage(content="오늘도 비슷해")],
        "persona": {"tone": ["차분하게"], "view": "듣기", "forbidden": []},
        "persona_turn": 1,
        "turn": 5,
        "previous_arc": arc,
        "arc": arc,
        "route": "empathy",
    }))

    assert model.calls.count("persona") == 1
    assert out["persona_turn"] == 5


async def test_persona_refreshes_immediately_when_the_direction_changes() -> None:
    model = FakeModel()
    node = persona_graph.build(model)
    previous_arc = {
        "phase": "공감중", "mode": "empathy", "trajectory": "정체", "user_stance": "털어놓기",
        "commitments": [], "do_not": [], "next_move": "듣기", "handoff": False,
    }
    current_arc = {
        **previous_arc,
        "phase": "정리중",
        "mode": "reason",
        "user_stance": "조언요청",
        "next_move": "선택지를 정리하기",
    }

    out = await node(cast(State, {
        "messages": [HumanMessage(content="그래서 뭘 먼저 해야 할까?")],
        "persona": {"tone": ["차분하게"], "view": "듣기", "forbidden": []},
        "persona_turn": 1,
        "turn": 2,
        "previous_arc": previous_arc,
        "arc": current_arc,
        "route": "reason",
    }))

    assert model.calls.count("persona") == 1
    assert out["persona_turn"] == 2


async def test_persona_refreshes_immediately_for_safety_events() -> None:
    previous_arc = {
        "phase": "공감중", "mode": "empathy", "trajectory": "정체", "user_stance": "털어놓기",
        "commitments": [], "do_not": [], "next_move": "듣기", "handoff": False,
    }
    cases = [
        ({**previous_arc, "phase": "위기"}, []),
        ({**previous_arc, "user_stance": "조언거절"}, []),
        (previous_arc, ["직업 이야기 먼저 꺼내지 않기"]),
    ]

    for arc, boundaries in cases:
        model = FakeModel()
        node = persona_graph.build(model)
        out = await node(cast(State, {
            "messages": [HumanMessage(content="그건 지금 말하고 싶지 않아")],
            "persona": {"tone": ["차분하게"], "view": "듣기", "forbidden": []},
            "persona_turn": 1,
            "turn": 2,
            "previous_arc": previous_arc,
            "arc": arc,
            "route": "empathy",
            "identity_boundaries": boundaries,
        }))

        assert model.calls.count("persona") == 1
        assert out["persona_turn"] == 2


async def test_blank_finalize_output_keeps_a_nonempty_draft() -> None:
    model = FakeModel(
        script={
            "orient": [
                '{"phase":"공감중","mode":"empathy","trajectory":"정체","user_stance":"털어놓기",'
                '"commitments":[],"do_not":[],"next_move":"듣기","handoff":false}'
            ],
            "empathy_write": ["오늘은 정말 지쳤겠다."],
            "finalize": [""],
        }
    )

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="오늘 너무 지쳤어")]})

    assert out["messages"][-1].content == "오늘은 정말 지쳤겠다."
    assert model.calls.count("finalize") == 1


async def test_review_uses_one_finalize_call_without_review_loops() -> None:
    model = FakeModel(script={"finalize": ["그 일 때문에 많이 지쳤겠다."]})

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="오늘 회사에서 진이 다 빠졌어.")], "turn": 1}
    )

    assert out["messages"][-1].content == "그 일 때문에 많이 지쳤겠다."
    assert model.calls.count("finalize") == 1
    assert "surface" not in model.calls
    assert "intent" not in model.calls
    assert "rewrite" not in model.calls


async def test_finalize_keeps_crisis_contacts_from_the_draft() -> None:
    model = FakeModel(
        script={
            "empathy_write": ["지금 위험하면 109나 정신건강위기 상담전화 1577-0199로 연락해."],
            "finalize": ["지금 혼자 있지 마."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="죽고 싶어")], "turn": 1}
    )

    assert "109" in out["messages"][-1].content
    assert "1577-0199" in out["messages"][-1].content
    assert model.calls.count("finalize") == 1


async def test_finalize_fixes_friend_tone_in_one_call() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"공감중","mode":"empathy","trajectory":"정체","user_stance":"털어놓기",'
                '"commitments":[],"do_not":[],"next_move":"따라가기","handoff":false}'
            ],
            "empathy_write": ["회의에서 무능해 보일까 걱정될 수 있겠다."],
            "finalize": ["회의 때문에 신경 쓰였겠다."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="내일 회의 생각하니 좀 신경 쓰여.")]}
    )

    assert out["messages"][-1].content == "회의 때문에 신경 쓰였겠다."
    assert model.calls.count("finalize") == 1


async def test_empty_local_edit_uses_a_nonempty_safe_fallback() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"공감중","mode":"empathy","trajectory":"정체","user_stance":"털어놓기",'
                '"commitments":[],"do_not":[],"next_move":"따라가기","handoff":false}'
            ],
            "empathy_write": ["회의에서 무능해 보일까 걱정될 수 있겠다."],
            "finalize": [""],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="내일 회의 생각하니 좀 신경 쓰여.")]}
    )

    assert str(out["messages"][-1].content).strip()
    assert model.calls.count("finalize") == 1


async def test_progress_report_drops_advice_after_one_local_fix() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"reason","trajectory":"진전","user_stance":"보고",'
                '"commitments":[],"do_not":[],"next_move":"따라가기","handoff":false}'
            ],
            "reason_write": ["잘하고 있어. 이제 회의 목적부터 찾아봐."],
            "finalize": ["좋아. 이제 핵심 하나만 잡자."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="자료 핵심도 표시해뒀어.")]}
    )

    assert out["messages"][-1].content == "좋아."
    assert model.calls.count("finalize") == 1


async def test_finalize_repairs_semantic_and_local_failures_once() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"reason","trajectory":"정체","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"선택","handoff":false}'
            ],
            "reason_write": ["그 느낌부터 정리해봐."],
            "finalize": ["선택지를 둘로 나눠보자."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="이직할지 말지 같이 정리해줘.")]}
    )

    assert out["messages"][-1].content == "선택지를 둘로 나눠보자."
    assert model.calls.count("finalize") == 1


async def test_crisis_guidance_survives_the_single_finalize_call() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "empathy_write": [
                "그 느낌이 크면 지금 109나 정신건강위기 상담전화 1577-0199로 연락해."
            ],
            "finalize": ["지금 위험하면 109나 정신건강위기 상담전화 1577-0199로 연락해."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="죽고 싶다는 생각이 들어.")]}
    )

    assert "109" in out["messages"][-1].content
    assert "1577-0199" in out["messages"][-1].content
    assert model.calls.count("finalize") == 1


async def test_clean_progress_uses_one_finalize_call() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"empathy","trajectory":"진전","user_stance":"보고",'
                '"commitments":[],"do_not":[],"next_move":"따라가기","handoff":false}'
            ],
            "empathy_write": ["오, 핵심까지 표시해뒀네."],
            "finalize": ["오, 핵심까지 표시해뒀네."],
        }
    )

    out = await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="자료 핵심도 표시해뒀어.")]}
    )

    assert out["messages"][-1].content == "오, 핵심까지 표시해뒀네."
    assert model.calls.count("finalize") == 1


async def test_explicit_request_uses_one_finalize_call() -> None:
    model = FakeModel(
        script={
            "decide": ["skip"],
            "orient": [
                '{"phase":"실행중","mode":"reason","trajectory":"진전","user_stance":"조언요청",'
                '"commitments":[],"do_not":[],"next_move":"선택","handoff":false}'
            ],
            "reason_write": ["이제 발표 순서를 정하면 돼."],
            "finalize": ["이제 발표 순서를 정하면 돼."],
        }
    )

    await build_graph(llm=model).ainvoke(
        {"messages": [HumanMessage(content="자료는 표시해뒀어. 이제 뭘 해야 해?")]}
    )

    assert model.calls.count("finalize") == 1


async def test_crisis_signal_skips_reask_without_an_llm_call() -> None:
    """질문 하나로 턴이 끝나면 그 턴에 상담 안내가 못 나감."""
    model = FakeModel(script={"decide": ["situation"]})

    out = await build_graph(llm=model).ainvoke({"messages": [HumanMessage(content="그냥 죽고 싶어")]})

    assert "prepare" not in model.calls  # 되묻기 판정 자체를 안 함
    assert out["asked"] is False
    assert out["messages"][-1].content == "들으니 많이 힘드셨겠어요."  # 질문이 아니라 답변


def test_reask_prompts_carry_the_crisis_paragraph() -> None:
    from app.graph.subgraphs.prepare import prompt as prepare_prompt
    from app.graph.subgraphs.prepare.analysis import prompt as analysis_prompt

    situation = " ".join(str(m.content) for m in prepare_prompt.situation_request([]))
    question = " ".join(str(m.content) for m in analysis_prompt.question_request(None))

    assert "109" in situation and "1577-0199" in situation
    assert "109" in question and "1577-0199" in question


def test_identity_prompts_carry_a_user_boundary() -> None:
    from app.graph.subgraphs.prepare import prompt as prepare_prompt

    understand = " ".join(
        str(message.content)
        for message in prepare_prompt.understand_request(
            [],
            {"identity_hint": "생활을 알아볼 때"},
            {"emotion_examples": ["답답함"], "intensity_examples": ["중간"]},
            askable=["day"],
            boundaries=["직업 얘기는 하지 마"],
        )
    )
    question = " ".join(
        str(message.content)
        for message in prepare_prompt.identity_request([], ["day"], [], boundaries=["직업 얘기는 하지 마"])
    )

    assert "직업 얘기는 하지 마" in understand
    assert "직업 얘기는 하지 마" in question


def test_crisis_signal_ignores_spacing_and_common_homonyms() -> None:
    """`죽고 싶어`만 목록에 있으면 채팅에서 더 흔한 `죽고싶어`가 통째로 빠짐."""
    from app import crisis, guide

    keywords = guide.load_shared(crisis.CRISIS_FILE).get("keywords", [])

    for text in ("죽고싶어", "살기싫다", "사라지고싶어", "아빠한테 맞았어"):
        assert crisis.has_signal(text, keywords), text
    for text in ("네 말이 맞았어", "시험 답이 맞았어", "비를 맞았어"):
        assert not crisis.has_signal(text, keywords), text


def test_crisis_keywords_live_in_one_place() -> None:
    """압축과 되묻기가 각자 사본을 들면 조용히 갈라짐."""
    from app import guide
    from app.session.compress import graph as compress_graph
    from app.graph.subgraphs.prepare import graph as prepare_graph

    shared = guide.load_shared("healer_crisis.json").get("keywords", [])

    assert shared
    assert "crisis_keywords" not in guide.load(compress_graph.__file__, compress_graph.CONFIG_FILE)
    assert "crisis_keywords" not in guide.load(prepare_graph.__file__, prepare_graph.CONFIG_FILE)
