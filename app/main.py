"""FastAPI. 페이지 하나, 채팅 하나, 설정 둘."""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from app import settings
from app.graph import ROUTER_NODE, build_graph
from app.llm import catalog

STATIC = Path(__file__).parent.parent / "static"

app = FastAPI(title="emotion-healer")
_checkpointer = MemorySaver()
graph = build_graph(checkpointer=_checkpointer)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class SettingsRequest(BaseModel):
    model: str
    effort: str


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/settings")
async def read_settings() -> dict:
    return {"current": settings.load(), "models": catalog.options()}


@app.post("/api/settings")
async def write_settings(req: SettingsRequest) -> settings.Settings:
    global graph
    if reason := catalog.problem(req.model, req.effort):
        raise HTTPException(status_code=400, detail=reason)
    saved = settings.save({"model": req.model, "effort": req.effort})
    # 모델은 그래프를 만들 때 정해진다. 다시 조립하되 checkpointer는 그대로 둬서
    # 진행 중인 대화가 끊기지 않게 한다
    graph = build_graph(checkpointer=_checkpointer)
    return saved


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream(req: ChatRequest) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": req.thread_id}}
    inputs = {"messages": [HumanMessage(content=req.message)]}
    try:
        # 테스트 결과 -> subgraphs=True 없이는 서브그래프 안쪽 토큰이 안 올라온다
        async for _ns, (chunk, meta) in graph.astream(
            inputs, config, stream_mode="messages", subgraphs=True
        ):
            # 라우터가 뱉는 판정 단어가 화면에 흘러가지 않게 막는다
            if meta.get("langgraph_node") == ROUTER_NODE:
                continue
            # 테스트 결과 -> 노드가 state에 쓴 완성본도 같이 흘러나온다. 새 글자는 청크뿐
            if not isinstance(chunk, AIMessageChunk):
                continue
            if text := str(chunk.content):
                yield _sse({"text": text})
    except Exception as exc:  # 에러를 화면에 띄운다. 안 그러면 스피너만 돈다
        yield _sse({"error": f"{type(exc).__name__}: {exc}"})
    yield _sse({"done": True})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
