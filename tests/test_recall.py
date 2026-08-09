"""과거 대화 확인 서브그래프."""

import threading

from langchain_core.messages import AIMessage

from app.graph.subgraphs.recall import run
from app.main import _normalize_recall_answer
from tests.conftest import SilentModel


class BridgeModel(SilentModel):
    async def ainvoke(self, input, config=None, *, stop=None, **kwargs):
        return AIMessage(content="잠깐, 전에 한 얘기 좀 보고 올게.")


class ServiceBridgeModel(SilentModel):
    async def ainvoke(self, input, config=None, *, stop=None, **kwargs):
        return AIMessage(content="응, 대화에서 찾아볼게!")


async def test_recall_subgraph_returns_a_bridge_and_exact_evidence(account) -> None:
    from app.session import transcript

    user_id = account["user_id"]
    transcript.append(user_id, "human", "제주도에서 길을 잃었던 적이 있어")

    result = await run(BridgeModel(), user_id, "전에 제주도 얘기한 거 기억나?")

    assert result["needed"] is True
    assert result["bridge"] == "잠깐, 전에 한 얘기 좀 보고 올게."
    assert "제주도에서 길을 잃었던 적이 있어" in result["context"]


async def test_recall_subgraph_does_nothing_during_an_ordinary_turn(account) -> None:
    result = await run(BridgeModel(), account["user_id"], "오늘 제주도 날씨 좋다")

    assert result == {"needed": False, "bridge": "", "context": "", "evidence_ids": []}


async def test_recall_bridge_rejects_service_language(account) -> None:
    from app.session import transcript

    transcript.append(account["user_id"], "human", "제주도에서 길을 잃었어")

    result = await run(ServiceBridgeModel(), account["user_id"], "전에 제주도 얘기 기억나?")

    assert result["bridge"] == "잠깐, 위에 좀 볼게."
    assert "대화에서" not in result["bridge"]
    assert "!" not in result["bridge"]
    assert "해도 돼" in result["context"]


async def test_recall_search_and_bridge_start_in_parallel(account, monkeypatch) -> None:
    from app.session import transcript

    bridge_started = threading.Event()
    overlapped = {"value": False}
    original_search = transcript.search

    def delayed_search(*args, **kwargs):
        overlapped["value"] = bridge_started.wait(0.5)
        return original_search(*args, **kwargs)

    class ParallelBridgeModel(SilentModel):
        async def ainvoke(self, input, config=None, *, stop=None, **kwargs):
            bridge_started.set()
            return AIMessage(content="잠깐, 위에 좀 볼게.")

    monkeypatch.setattr(transcript, "search", delayed_search)
    transcript.append(account["user_id"], "human", "제주도에서 길을 잃었어")

    await run(ParallelBridgeModel(), account["user_id"], "전에 제주도 얘기 기억나?")

    assert overlapped["value"] is True


def test_missing_recall_answer_normalizes_ai_time_phrasing() -> None:
    answer = "그 얘기는 못 찾겠어. 언제쯤 말했는지 기억나?"

    assert _normalize_recall_answer(answer, has_evidence=False) == "그 얘기는 못 찾겠어. 언제 말했는지 기억나?"
    assert _normalize_recall_answer("어느 때쯤 말했어?", has_evidence=False) == "언제 말했어?"
    assert _normalize_recall_answer(answer, has_evidence=True) == answer
