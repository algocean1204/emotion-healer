"""큐레이터 서브그래프. START → need ─┬─ 쓸모없음 → finish
                              └─ expand → query → judge ─┬─ 충분 → card → finish
                                            ↑              └─ 부족 → expand (상한까지)
                                            └──────────────┘"""

from __future__ import annotations

import json
from typing import NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app import guide
from app.session.ontology import graph_store
from app.session.ontology import memory_pack
from app.session.ontology.curator import prompt
from app.session.ontology.retrieve import cap_resident, matches_focus
from app.session.store import Session

CONFIG_FILE = "healer_ontology.json"


class CuratorState(TypedDict):
    """session·thread_id만 입력으로 받고 나머지는 노드가 채움."""

    session: Session
    thread_id: str
    need: NotRequired[bool]
    queries: NotRequired[list[str]]
    round: NotRequired[int]
    candidates: NotRequired[list[dict]]
    missing: NotRequired[str]
    sufficient: NotRequired[bool]
    memory: NotRequired[dict]
    result: NotRequired[Session]


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _parse_json(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _recent_text(session: Session, count: int) -> str:
    """최근 count개 메시지의 내용만 연결. '이번 대화'의 근거로 사용."""
    recent = session.get("messages", [])[-count:]
    contents = [str(message.get("data", {}).get("content", "")) for message in recent]
    return "\n".join(content for content in contents if content)


def build(llm: BaseChatModel):
    config = _config()
    max_rounds = config.get("curator_max_rounds", 3)  # expand 총 호출 상한(최초 포함)
    candidate_limit = config.get("curator_candidate_limit", 5)
    recent_messages = config.get("curator_recent_messages", 4)
    memory_pack_ttl = int(config.get("memory_pack_ttl_seconds", 86400))

    async def need(state: CuratorState) -> dict:
        ai = await llm.ainvoke(prompt.need_request(_recent_text(state["session"], recent_messages)))
        return {"need": bool(_parse_json(str(ai.content)).get("need", False))}

    def pick_need(state: CuratorState) -> str:
        return "expand" if state.get("need") else "finish"

    async def expand(state: CuratorState) -> dict:
        text = _recent_text(state["session"], recent_messages)
        ai = await llm.ainvoke(prompt.expand_request(text, state.get("missing", "")))
        queries = [str(item).strip() for item in _parse_json(str(ai.content)).get("queries", []) if str(item).strip()]
        return {"queries": queries, "round": state.get("round", 0) + 1}

    def query(state: CuratorState) -> dict:
        """온톨로지 조회. 코드만, LLM 없음."""
        active = [node for node in graph_store.nodes(state["thread_id"]) if node["status"] == "active"]
        matched = [node for node in active if matches_focus(node, state.get("queries", []))]
        return {"candidates": cap_resident(matched, candidate_limit)}

    async def judge(state: CuratorState) -> dict:
        text = _recent_text(state["session"], recent_messages)
        ai = await llm.ainvoke(prompt.judge_request(text, state.get("candidates", [])))
        parsed = _parse_json(str(ai.content))
        return {"sufficient": bool(parsed.get("sufficient", True)), "missing": str(parsed.get("missing", ""))}

    def pick_judge(state: CuratorState) -> str:
        if state.get("sufficient", True) or state.get("round", 0) >= max_rounds:
            return "card"
        return "expand"

    async def card(state: CuratorState) -> dict:
        candidates = state.get("candidates", [])
        quiet_nodes = [
            node for node in candidates if node.get("disclosure", "quiet") != "proactive" and not node.get("crisis")
        ]
        tone_lines: list[str] = []
        if quiet_nodes:
            ai = await llm.ainvoke(prompt.card_request(quiet_nodes))
            tone_lines = [str(line).strip() for line in _parse_json(str(ai.content)).get("tone_lines", []) if str(line).strip()]

        # proactive 목록은 게이트가 라이브 노드에서 다시 계산함. 여기서 만들면
        # 전건 조회 한 번을 더 태우고 아무도 안 읽음
        return {"memory": memory_pack.create(candidates, tone_lines, memory_pack_ttl)}

    def finish(state: CuratorState) -> dict:
        memory = state.get("memory") or memory_pack.create([], [], memory_pack_ttl)
        return {"result": {**state["session"], "memory": memory}}

    builder = StateGraph(CuratorState)
    builder.add_node("need", need)
    builder.add_node("expand", expand)
    builder.add_node("query", query)
    builder.add_node("judge", judge)
    builder.add_node("card", card)
    builder.add_node("finish", finish)
    builder.add_edge(START, "need")
    builder.add_conditional_edges("need", pick_need, {"expand": "expand", "finish": "finish"})
    builder.add_edge("expand", "query")
    builder.add_edge("query", "judge")
    builder.add_conditional_edges("judge", pick_judge, {"card": "card", "expand": "expand"})
    builder.add_edge("card", "finish")
    builder.add_edge("finish", END)
    return builder.compile()


async def curate(session: Session, llm: BaseChatModel, thread_id: str) -> Session:
    """세션 하나를 큐레이터 그래프에 태워 memory를 채운 세션을 받음."""
    out = await build(llm).ainvoke({"session": session, "thread_id": thread_id})
    return out["result"]
