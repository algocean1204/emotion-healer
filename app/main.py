"""FastAPI. 페이지 하나, 채팅 엔드포인트 하나."""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel

from app.graph import build_graph

load_dotenv()

STATIC = Path(__file__).parent.parent / "static"

app = FastAPI(title="emotion-healer")
graph = build_graph()


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


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
        async for chunk, _meta in graph.astream(
            inputs, config, stream_mode="messages"
        ):
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
