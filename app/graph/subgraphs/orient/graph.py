"""대화 방향(orient) 서브그래프. 툴 없이 국면·모드·궤적만 정함.

route 일회 분류를 대체함. 오래 아는 친구처럼 이어가려면 매 턴 라벨이 아니라
직전 arc 를 보고 이번 전략을 고름.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app import guide
from app.graph.state import State
from app.graph.subgraphs.orient import prompt
from app.types import Arc, Route

CONFIG_FILE = "healer_orient.json"

_EMPTY_ARC: Arc = {
    "phase": "열림",
    "mode": "empathy",
    "trajectory": "불명",
    "user_stance": "불명",
    "commitments": [],
    "do_not": [],
    "next_move": "",
    "handoff": False,
}


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _parse(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_items(value: object, limit: int) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:limit]
    return []


def normalize(raw: dict, config: dict | None = None) -> Arc:
    """모델 출력을 허용 값만 남긴 Arc 로 만듦. 밖에서도 테스트함."""
    cfg = config or _config()
    phases = set(cfg.get("phases", []))
    trajectories = set(cfg.get("trajectories", []))
    stances = set(cfg.get("stances", []))
    modes = set(cfg.get("modes", ["empathy", "reason", "both"]))
    max_commitments = int(cfg.get("max_commitments", 4))
    max_do_not = int(cfg.get("max_do_not", 4))
    max_move = int(cfg.get("max_next_move_chars", 80))

    mode_raw = str(raw.get("mode", "empathy")).strip().lower()
    mode: Route = "empathy"
    if mode_raw in modes:
        mode = mode_raw  # type: ignore[assignment]
    elif "reason" in mode_raw and "empathy" not in mode_raw:
        mode = "reason"
    elif "both" in mode_raw:
        mode = "both"

    handoff = bool(raw.get("handoff", False))
    # both 인데 handoff 가 아니면 공감만 — 한 턴 이중 작성 남용 방지
    if mode == "both" and not handoff:
        mode = "empathy"

    phase = str(raw.get("phase", "열림")).strip()
    if phase not in phases:
        phase = "열림"
    trajectory = str(raw.get("trajectory", "불명")).strip()
    if trajectory not in trajectories:
        trajectory = "불명"
    stance = str(raw.get("user_stance", "불명")).strip()
    if stance not in stances:
        stance = "불명"

    return {
        "phase": phase,
        "mode": mode,
        "trajectory": trajectory,
        "user_stance": stance,
        "commitments": _as_items(raw.get("commitments"), max_commitments),
        "do_not": _as_items(raw.get("do_not"), max_do_not),
        "next_move": str(raw.get("next_move", ""))[:max_move],
        "handoff": handoff and mode == "both",
    }


def empty_arc() -> Arc:
    return {
        "phase": _EMPTY_ARC["phase"],
        "mode": _EMPTY_ARC["mode"],
        "trajectory": _EMPTY_ARC["trajectory"],
        "user_stance": _EMPTY_ARC["user_stance"],
        "commitments": [],
        "do_not": [],
        "next_move": "",
        "handoff": False,
    }


def build(llm: BaseChatModel):
    """orient 서브그래프. sense 한 노드."""
    config = _config()

    async def sense(state: State) -> dict:
        ai = await llm.ainvoke(
            prompt.sense_request(
                state["messages"],
                state.get("feeling"),
                state.get("previous_arc"),
                state.get("identity_wants"),
            )
        )
        arc = normalize(_parse(str(ai.content)), config)
        # 이후 persona·write·분기가 쓰는 route 는 arc.mode 와 같게 맞춤
        return {"arc": arc, "route": arc["mode"]}

    builder = StateGraph(State)
    builder.add_node("sense", sense)
    builder.add_edge(START, "sense")
    builder.add_edge("sense", END)
    return builder.compile()
