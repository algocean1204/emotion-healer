"""그래프가 주고받는 상태."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import MessagesState

Route = Literal["empathy", "solution"]


class State(MessagesState):
    """messages는 MessagesState가 준다. route는 라우터가 채운다."""

    route: Route
