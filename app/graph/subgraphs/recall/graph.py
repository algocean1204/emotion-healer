"""명시적인 회상 요청만 원문 검색으로 보내는 서브그래프."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from app.session import transcript

_FALLBACK_BRIDGE = "잠깐, 위에 좀 볼게."
_SERVICE_BRIDGE_PHRASES = ("대화에서", "기록에서", "확인할게", "확인해볼게", "찾아드릴")


class RecallState(TypedDict):
    user_id: str
    query: str
    needed: NotRequired[bool]
    evidence: NotRequired[list[dict]]
    evidence_ids: NotRequired[list[int]]
    bridge: NotRequired[str]
    context: NotRequired[str]


def build(llm: BaseChatModel):
    def gate(state: RecallState) -> dict:
        return {"needed": transcript.needs_recall(state["query"])}

    def pick(state: RecallState) -> str | list[str]:
        return ["search", "bridge"] if state.get("needed") else END

    def search(state: RecallState) -> dict:
        evidence = transcript.search(state["user_id"], state["query"])
        return {
            "evidence": evidence,
            "evidence_ids": [message["id"] for message in evidence],
            "context": transcript.recall_context(evidence),
        }

    async def bridge(state: RecallState) -> dict:
        try:
            ai = await llm.ainvoke([
                SystemMessage(content=(
                    "사용자가 예전에 한 말을 확인해 달라고 했다. 잠깐 위를 훑어보겠다는 말만 한 문장으로 한다. "
                    "친한 한국인 친구 말투로, 따지거나 생색내지 말고, 답을 이미 찾은 척하지 않는다. "
                    "'대화에서', '기록에서', '확인할게' 같은 서비스 안내 표현과 느낌표는 쓰지 않는다. 35자 이내."
                )),
                SystemMessage(content=f"현재 말: {state['query']}"),
            ])
            text = str(ai.content).strip().splitlines()[0][:60]
        except Exception:
            text = ""
        if "!" in text or any(phrase in text for phrase in _SERVICE_BRIDGE_PHRASES):
            text = ""
        return {"bridge": text or _FALLBACK_BRIDGE}

    def join(state: RecallState) -> dict:
        del state
        return {}

    graph = StateGraph(RecallState)
    graph.add_node("gate", gate)
    graph.add_node("search", search)
    graph.add_node("bridge", bridge)
    graph.add_node("join", join)
    graph.add_edge(START, "gate")
    graph.add_conditional_edges("gate", pick, {"search": "search", "bridge": "bridge", END: END})
    graph.add_edge("search", "join")
    graph.add_edge("bridge", "join")
    graph.add_edge("join", END)
    return graph.compile()


async def run(llm: BaseChatModel, user_id: str, query: str) -> dict:
    if not transcript.needs_recall(query):
        return {"needed": False, "bridge": "", "context": "", "evidence_ids": []}
    result = await build(llm).ainvoke({"user_id": user_id, "query": query})
    return {
        "needed": bool(result.get("needed")),
        "bridge": str(result.get("bridge", "")),
        "context": str(result.get("context", "")),
        "evidence_ids": list(result.get("evidence_ids", [])),
    }
