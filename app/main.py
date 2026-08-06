"""FastAPI. 채팅 잡 셋, 설정 둘, 기억 셋. 화면은 nginx가 따로 서빙함."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Coroutine, Literal, TypedDict, cast

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, field_validator

from app import guide, opening, session, settings
from app.auth import current_user, router as auth_router
from app.graph import build_graph
from app.graph.state import State
from app.llm import catalog
from langchain_core.language_models import BaseChatModel

from app.llm.provider import get_chat_model
from app.llm.trace import TurnTrace
from app.session.compress import run as compress_session
from app.session.ontology import build_context as ontology_build_context
from app.session.ontology import graph_store as ontology_graph
from app.session.ontology import identity as ontology_identity
from app.session.ontology import curator as ontology_curator
from app.session.remember import remember
from app import crisis as crisis_mod
from app.settings.store import Settings

log = logging.getLogger(__name__)

PROGRESS_FILE = "healer_progress.json"
JOB_FILE = "healer_job.json"
app = FastAPI(title=guide.load_shared("healer_service.json").get("name", ""))
app.include_router(auth_router)

# (model, effort) → (llm, graph). 사용자마다 설정이 달라도 같은 조합은 재사용함
_runtime_cache: dict[tuple[str, str], tuple[BaseChatModel, Any]] = {}


def _runtime(user_id: str) -> tuple[BaseChatModel, Any]:
    cfg = settings.load(user_id)
    key = (cfg["model"], cfg["effort"])
    found = _runtime_cache.get(key)
    if found is not None:
        return found
    # llm 을 넘기면 테스트 경로와 같이 주입 모드. 운영은 조합당 한 번만 조립
    chat = get_chat_model(cfg)
    compiled = build_graph(chat)
    _runtime_cache[key] = (chat, compiled)
    return chat, compiled


class ChatRequest(BaseModel):
    message: str
    session_id: str


class OpeningRequest(BaseModel):
    timezone: str = "Asia/Seoul"


class MemoryEditRequest(BaseModel):
    subject: str
    predicate: str
    object: str

    @field_validator("subject", "predicate", "object")
    @classmethod
    def clean_part(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("기억 문장은 비워둘 수 없습니다.")
        if len(cleaned) > 160:
            raise ValueError("기억 문장은 항목마다 160자까지 쓸 수 있습니다.")
        return cleaned


class SettingsRequest(BaseModel):
    model: str
    effort: str




class Job(TypedDict):
    """진행 중인 채팅 잡 하나. 프로세스 내부 dict가 전체 저장소."""

    status: Literal["running", "done", "error"]
    step: str | None
    text: str
    error: str
    session_id: str
    # 시작 시각이 없으면 매달린 잡을 회수할 기준도, 어디가 느린지 잴 기준도 없음
    started_at: float
    finished_at: float
    trace: dict[str, Any]


jobs: dict[str, Job] = {}
# asyncio는 task를 약한 참조로만 들고 있음. 참조를 안 잡아두면 도중에 GC될 수 있음
_running_tasks: set[asyncio.Task] = set()
# 취소하려면 잡에서 태스크를 되찾을 수 있어야 함
_tasks_by_job: dict[str, asyncio.Task] = {}


@app.get("/api/settings")
async def read_settings(user_id: str = Depends(current_user)) -> dict:
    return {"current": settings.load(user_id), "models": catalog.options()}


@app.post("/api/settings")
async def write_settings(
    req: SettingsRequest, user_id: str = Depends(current_user)
) -> Settings:
    if reason := catalog.problem(req.model, req.effort):
        raise HTTPException(status_code=400, detail=reason)
    # 사용자별 Postgres 저장. 전역 파일을 덮지 않음
    saved = settings.save(user_id, {"model": req.model, "effort": req.effort})
    # 캐시를 비우면 다음 턴에 새 조합으로 조립됨
    _runtime_cache.pop((saved["model"], saved["effort"]), None)
    return saved


@app.get("/api/sessions")
async def list_sessions(user_id: str = Depends(current_user)) -> dict:
    return {"sessions": session.list_for_user(user_id)}


@app.post("/api/sessions", status_code=201)
async def create_session(user_id: str = Depends(current_user)) -> dict:
    session_id = session.new_session_id(user_id)
    session.save(session_id, session.empty(user_id, session_id))
    return {"session_id": session_id}


def _owned(session_id: str, user_id: str) -> str:
    """남의 세션은 없는 것으로 처리. 존재 여부도 외부에 공개하지 않음."""
    if session.owner_of(session_id) != user_id:
        raise HTTPException(status_code=404, detail="모르는 세션입니다.")
    return session_id


@app.get("/api/sessions/{session_id}")
async def read_session(session_id: str, user_id: str = Depends(current_user)) -> dict:
    stored = session.load(_owned(session_id, user_id))
    return {
        "session_id": session_id,
        "created_at": stored["created_at"],
        "messages": [
            {"role": message.get("type"), "text": str(message.get("data", {}).get("content", ""))}
            for message in stored["messages"]
        ],
    }


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user_id: str = Depends(current_user)) -> None:
    session.remove(_owned(session_id, user_id))


@app.post("/api/sessions/{session_id}/opening", status_code=202)
async def create_opening(
    session_id: str,
    req: OpeningRequest,
    response: Response,
    user_id: str = Depends(current_user),
) -> dict:
    _owned(session_id, user_id)
    current = session.load(session_id)
    if current["messages"] and _human_turn_count(current["messages"]) == 0:
        response.status_code = 200
        return {"needed": False}
    user_sessions = [
        session.load(item["session_id"])
        for item in session.list_for_user(user_id)
    ]
    if not any(stored["session_id"] == session_id for stored in user_sessions):
        user_sessions.append(current)
    contact_at = opening.latest_contact_at(user_sessions)
    now = datetime.now(timezone.utc)
    planned = opening.timing(contact_at, now=now, timezone_name=req.timezone)
    if current.get("opening_key") == planned["key"]:
        response.status_code = 200
        return {"needed": False}

    _sweep_jobs()
    if job_id := _running_job_id(session_id):
        return {"needed": True, "job_id": job_id, "accepted": False}
    job_id = _start_job(
        session_id,
        lambda found: _run_opening(found, session_id, req.timezone, contact_at, now),
        initial_step="채팅창 여는 중…",
    )
    return {"needed": True, "job_id": job_id, "accepted": True}


@app.get("/api/memory")
async def read_memory(user_id: str = Depends(current_user)) -> dict:
    """활성 기억과 연결 화면에 필요한 한 벌의 데이터를 돌려줌."""
    return _memory_payload(user_id)


def _memory_payload(user_id: str) -> dict:
    nodes = ontology_graph.nodes(user_id)
    entity_names: dict[str, None] = {}
    statements = []
    for node in nodes:
        entity_names[node["subject"]] = None
        entity_names[node["object"]] = None
        statements.append(
            {
                "id": node["id"],
                "subject": node["subject"],
                "predicate": node["predicate"],
                "object": node["object"],
                "slot": node.get("slot"),
                "disclosure": node.get("disclosure", "quiet"),
                "crisis": node.get("crisis", False),
                "status": node["status"],
            }
        )
    return {
        "nodes": statements,
        "graph": {
            "entities": [{"id": name, "label": name} for name in entity_names],
            "statements": statements,
        },
        "slots": ontology_identity.filled_slots(user_id),
        "slot_labels": ontology_identity.SLOT_LABELS,
    }


@app.post("/api/memory/{node_id}/retract")
async def retract_memory(
    node_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user),
) -> dict:
    result = _apply_memory_action(node_id, user_id, ontology_graph.retract)
    background_tasks.add_task(_recurate_latest_memory, user_id)
    return result


@app.post("/api/memory/{node_id}/quiet")
async def quiet_memory(
    node_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user),
) -> dict:
    result = _apply_memory_action(node_id, user_id, ontology_graph.quiet)
    background_tasks.add_task(_recurate_latest_memory, user_id)
    return result


@app.post("/api/memory/{node_id}/edit")
async def edit_memory(
    node_id: str,
    req: MemoryEditRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user),
) -> dict:
    if not ontology_graph.update(
        user_id,
        node_id,
        subject=req.subject,
        predicate=req.predicate,
        object_=req.object,
    ):
        raise HTTPException(status_code=404, detail=f"모르는 node_id입니다: {node_id}")
    result = _after_memory_change(user_id)
    background_tasks.add_task(_recurate_latest_memory, user_id)
    return result


def _apply_memory_action(node_id: str, user_id: str, action: Callable[[str, str], bool]) -> dict:
    if not action(user_id, node_id):
        raise HTTPException(status_code=404, detail=f"모르는 node_id입니다: {node_id}")
    return _after_memory_change(user_id)


def _after_memory_change(user_id: str) -> dict:
    # 큐레이터가 만들어둔 배경에는 노드 사본과 거기서 뽑은 톤 문장이 들어 있음.
    # 세션마다 따로 들고 있으므로 그 사용자의 세션 전부에서 비움
    for item in session.list_for_user(user_id):
        stored = session.load(item["session_id"])
        if stored["memory"]:
            stored["memory"] = {}
            session.save(item["session_id"], stored)
    return _memory_payload(user_id)


async def _recurate_latest_memory(user_id: str) -> None:
    """최근 대화 한 건의 검색 후보만 남은 활성 기억으로 다시 만듦."""
    latest = next(
        (
            session.load(item["session_id"])
            for item in session.list_for_user(user_id)
            if item["turns"] > 0
        ),
        None,
    )
    if latest is None or not ontology_graph.has_active(user_id):
        return
    try:
        llm, _ = _runtime(user_id)
        curated = await ontology_curator.curate(latest, llm, user_id)
        fresh = session.load(latest["session_id"])
        fresh["memory"] = curated["memory"]
        session.save(latest["session_id"], fresh)
    except Exception:
        log.exception("기억 재큐레이션 실패 user=%s", user_id)


@app.post("/api/chat", status_code=202)
async def chat(req: ChatRequest, user_id: str = Depends(current_user)) -> dict:
    _owned(req.session_id, user_id)
    # 상한이 없으면 긴 입력 한 방으로 컨텍스트와 비용이 함께 터짐
    limit = int(guide.load(__file__, JOB_FILE).get("max_message_chars", 4000))
    if len(req.message) > limit:
        raise HTTPException(status_code=413, detail=f"{limit}자까지 보낼 수 있어요.")
    _sweep_jobs()
    if job_id := _running_job_id(req.session_id):
        # accepted=false 면 프론트가 새 메시지 전송으로 착각하지 않음
        return {"job_id": job_id, "accepted": False}
    job_id = _start_job(req.session_id, lambda found: _run(found, req))
    return {"job_id": job_id, "accepted": True}


def _running_job_id(session_id: str) -> str | None:
    for job_id, job in jobs.items():
        if job["session_id"] == session_id and job["status"] == "running":
            return job_id
    return None


def _start_job(
    session_id: str,
    run: Callable[[str], Coroutine[Any, Any, None]],
    *,
    initial_step: str | None = None,
) -> str:
    """일반 답변과 첫 안부가 같은 세션 잠금·취소·회수 규칙을 씀."""
    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "running",
        "step": initial_step,
        "text": "",
        "error": "",
        "session_id": session_id,
        "started_at": time.time(),
        "finished_at": 0.0,
        "trace": {},
    }
    task = asyncio.create_task(run(job_id))
    _tasks_by_job[job_id] = task
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    task.add_done_callback(lambda _: _tasks_by_job.pop(job_id, None))
    return job_id


@app.post("/api/chat/{job_id}/cancel")
async def chat_cancel(job_id: str, user_id: str = Depends(current_user)) -> dict:
    """진짜로 멈춤. 잡만 놔두면 다음 메시지가 중복 방지에 걸려 조용히 버려짐."""
    _own_job(job_id, user_id)
    task = _tasks_by_job.pop(job_id, None)
    if task is not None:
        task.cancel()
    jobs.pop(job_id, None)
    return {"cancelled": True}


@app.get("/api/chat/{job_id}")
async def chat_status(job_id: str, user_id: str = Depends(current_user)) -> dict:
    job = _own_job(job_id, user_id)
    if job["status"] == "running":
        return {"status": "running", "step": job["step"]}
    if job["status"] == "done":
        return {"status": "done", "text": job["text"]}
    return {"status": "error", "error": job["error"]}


def _own_job(job_id: str, user_id: str) -> Job:
    """잡도 세션에 속함. 남의 잡은 없는 것으로 봄."""
    job = jobs.get(job_id)
    if job is None or session.owner_of(job["session_id"]) != user_id:
        raise HTTPException(status_code=404, detail=f"모르는 job_id입니다: {job_id}")
    return job


def _sweep_jobs() -> None:
    """끝난 잡은 TTL 뒤에 치우고, 너무 오래 도는 잡은 끊음.

    running을 그냥 두면 중복 방지가 그 세션의 새 메시지를 전부 옛 잡으로 돌려보내
    재시작 전까지 대화가 막힘. 상한을 넘긴 잡은 실패로 마감함.
    """
    config = guide.load(__file__, JOB_FILE)
    ttl = config.get("ttl_seconds", 300)
    limit = config.get("max_run_seconds", 600)
    now = time.time()

    for job_id, job in list(jobs.items()):
        if job["status"] == "running" and now - job["started_at"] > limit:
            log.warning(
                "잡 상한 초과로 끊음 job=%s session=%s 경과=%.0f초",
                job_id,
                job["session_id"],
                now - job["started_at"],
            )
            task = _tasks_by_job.pop(job_id, None)
            if task is not None:
                task.cancel()
            _finish_error(job_id, "답변이 너무 오래 걸려 멈췄어요. 다시 보내주세요.")

    stale = [
        job_id
        for job_id, job in jobs.items()
        if job["status"] != "running" and now - job["finished_at"] > ttl
    ]
    for job_id in stale:
        del jobs[job_id]


async def _run(job_id: str, req: ChatRequest) -> None:
    """무슨 일이 있어도 잡을 running에 남기지 않음. 취소도 여기서 마무리함."""
    try:
        await _run_turn(job_id, req)
    except asyncio.CancelledError:
        _finish_error(job_id, "취소했어요.")
        raise
    except Exception:
        # 원문은 로그로만. 화면에 스택이나 DSN이 나가면 감정 지원 화면이 아니게 됨
        job = jobs.get(job_id)
        log.exception(
            "턴 실패 job=%s session=%s 단계=%s",
            job_id,
            job["session_id"] if job else "?",
            job["step"] if job else "?",
        )
        _finish_error(job_id, "답변을 만들지 못했어요. 다시 보내주세요.")


async def _run_opening(
    job_id: str,
    session_id: str,
    timezone_name: str,
    contact_at: str | None,
    now: datetime,
) -> None:
    """사람 발화 없이 만드는 첫 안부. 일반 그래프에 가짜 HumanMessage를 넣지 않음."""
    try:
        stored = session.load(session_id)
        user_id = stored["user_id"]
        llm, _ = _runtime(user_id)
        result = await opening.compose(
            stored,
            llm,
            timezone_name=timezone_name,
            now=now,
            contact_at=contact_at,
            candidates=opening.allowed_candidates(user_id),
        )
        fresh = session.load(session_id)
        fresh["messages"] = session.from_messages(
            [*session.to_messages(fresh), AIMessage(content=result["text"])]
        )
        fresh["last_assistant_at"] = datetime.now(timezone.utc).isoformat()
        fresh["opening_key"] = result["timing"]["key"]
        fresh["pending_hypothesis"] = result["pending_hypothesis"]
        session.save(session_id, fresh)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["text"] = result["text"]
        jobs[job_id]["finished_at"] = time.time()
    except asyncio.CancelledError:
        _finish_error(job_id, "취소했어요.")
        raise
    except Exception:
        log.exception("첫 안부 실패 job=%s session=%s", job_id, session_id)
        _finish_error(job_id, "첫 인사를 만들지 못했어요. 잠시 뒤 다시 열어주세요.")


def _finish_error(job_id: str, message: str) -> None:
    job = jobs.get(job_id)
    if job is None or job["status"] != "running":
        return
    job["status"] = "error"
    job["error"] = message
    job["finished_at"] = time.time()


def _human_turn_count(messages: list) -> int:
    """세션 JSON 의 messages_to_dict 형태 기준."""
    return sum(1 for message in messages if message.get("type") == "human")


async def _run_turn(job_id: str, req: ChatRequest) -> None:
    trace = TurnTrace()
    progress = guide.load(__file__, PROGRESS_FILE)
    stored = session.load(req.session_id)
    user_id = stored["user_id"]
    user_at = datetime.now(timezone.utc).isoformat()
    history = session.to_messages(stored)
    user_message = HumanMessage(content=req.message)
    if not history or not isinstance(history[-1], HumanMessage) or history[-1].content != req.message:
        history.append(user_message)
    stored["messages"] = session.from_messages(history)
    stored["last_user_at"] = user_at
    session.save(req.session_id, stored)

    llm, graph = _runtime(user_id)
    # 온톨로지 배경은 이번 그래프 입력에만 넣음. 저장까지 새면 다음 턴마다 쌓임
    turn_messages = cast(list[AnyMessage], history)
    background = ontology_build_context(stored, req.message, user_id)
    hypothesis = opening.hypothesis_context(stored, user_id)
    context = "\n".join(item for item in (background, hypothesis) if item)
    if context:
        turn_messages = cast(list[AnyMessage], [SystemMessage(content=context), *turn_messages])

    # 이번 턴 번호(방금 말 포함). 정체성 질문 창·간격 계산에 씀
    turn = _human_turn_count(stored["messages"])
    last_id_turn = stored.get("last_identity_turn")
    since = (turn - int(last_id_turn)) if last_id_turn is not None else None
    crisis_keywords = guide.load_shared(crisis_mod.CRISIS_FILE).get("keywords", [])
    in_crisis = crisis_mod.has_signal(req.message, crisis_keywords)
    intensity = (stored.get("feeling") or {}).get("intensity") if stored.get("feeling") else None
    filled = ontology_identity.filled_slots(user_id)
    askable = ontology_identity.askable_slots(
        user_id,
        turn=turn,
        identity_asks=int(stored.get("identity_asks") or 0),
        turns_since_identity=since,
        crisis=in_crisis,
        intensity=intensity,
    )
    inputs: State = {
        "messages": turn_messages,
        "asked": stored["asked"],
        "feeling": stored["feeling"],
        "persona": stored["persona"],
        "askable_slots": askable,
        "identity_wants": filled.get("want", []),
        "identity_boundaries": filled.get("boundary", []),
        # 직전 답변 턴의 궤적. orient 가 읽고 친구처럼 이어감
        "previous_arc": stored.get("arc"),
    }

    # 테스트 결과 -> subgraphs=True 조합의 반환 타입이 stub에서 하나로 안 좁혀져 손으로 명시함
    stream = cast(
        "AsyncIterator[tuple[tuple[str, ...], dict[str, Any]]]",
        graph.astream(
            inputs,
            stream_mode="updates",
            subgraphs=True,
            config={"callbacks": [trace]},
        ),
    )
    collected: dict[str, Any] = {}
    last_step = ""
    async for namespace, update in stream:
        for node_name, value in update.items():
            if value and namespace == ():
                collected.update(value)
            step = progress.get(node_name)
            if step and step != last_step:
                last_step = step
                jobs[job_id]["step"] = step
    final_messages = collected.get("messages", inputs["messages"])
    # 그래프가 덧붙인 만큼만 가져옴. 배경 SystemMessage는 여기서 자연히 빠짐
    new_messages = final_messages[len(turn_messages):]
    # both는 공감·방법을 각각 붙여 답이 둘임. [-1]만 담으면 방법만 보이고
    # 공감은 새로고침해야 나타남 — 공감 뒤 방법이라는 순서 그대로 이어 붙임
    text = "\n\n".join(str(message.content) for message in new_messages if str(message.content).strip())
    if not text and final_messages:
        text = str(final_messages[-1].content)
    # 앞 턴의 배경 작업이 그 사이 memory를 채웠을 수 있음. 통째로 저장하면 그걸 덮어
    # 큐레이터가 만든 배경이 매번 사라짐. 이 턴이 만든 필드만 얹음
    fresh = session.load(req.session_id)
    fresh["messages"] = session.from_messages([*history, *new_messages])
    fresh["feeling"] = collected.get("feeling", stored["feeling"])
    fresh["persona"] = collected.get("persona", stored["persona"])
    fresh["asked"] = collected.get("asked", False)
    fresh["opened_topics"] = stored["opened_topics"]
    fresh["last_user_at"] = user_at
    fresh["last_assistant_at"] = datetime.now(timezone.utc).isoformat()
    fresh["pending_hypothesis"] = None
    # 답변 턴에서만 arc 갱신. 질문만 한 턴은 직전 궤적을 유지함
    if collected.get("arc") is not None:
        fresh["arc"] = collected.get("arc")
    else:
        fresh["arc"] = stored.get("arc")
    # 정체성 질문을 냈으면 세션 카운터를 올림 — 다음 턴 askable 창이 이걸 봄
    if collected.get("ask") == "identity":
        fresh["identity_asks"] = int(stored.get("identity_asks") or 0) + 1
        fresh["last_identity_turn"] = turn
    else:
        fresh["identity_asks"] = stored.get("identity_asks", 0)
        fresh["last_identity_turn"] = stored.get("last_identity_turn")
    session.save(req.session_id, fresh)

    trace.finish_response()
    jobs[job_id]["trace"] = trace.summary()
    jobs[job_id]["status"] = "done"
    jobs[job_id]["text"] = text
    jobs[job_id]["finished_at"] = time.time()

    # 여기서부터 폴링 쪽은 이미 done 수신 완료
    trace.start_background()
    traced_llm = cast(BaseChatModel, llm.with_config(callbacks=[trace]))
    await _after_turn(req.session_id, user_id, traced_llm)
    trace.finish_background()
    if job_id in jobs:
        jobs[job_id]["trace"] = trace.summary()
        log.info("턴 계측 job=%s trace=%s", job_id, json.dumps(jobs[job_id]["trace"]))


async def _after_turn(session_id: str, user_id: str, llm: BaseChatModel) -> None:
    """기억은 매 턴, 압축은 임계를 넘을 때만. 어느 쪽이 실패해도 방금 저장한 세션은 그대로 둠."""
    stored = session.load(session_id)
    try:
        remembered = await remember(stored, llm, user_id)
        # 이 작업이 도는 수십 초 사이 다음 턴이 세션을 저장했을 수 있음.
        # 통째로 덮으면 그 턴의 메시지가 사라지므로 이 작업이 만든 필드만 얹음
        stored = session.load(session_id)
        stored["memory"] = remembered["memory"]
        session.save(session_id, stored)
    except Exception:
        # 조용히 넘기면 "기억할 게 없었다"와 구분 불가. stored는 실패 전 값 유지
        log.exception("기억 만들기 실패 session=%s", session_id)
    try:
        compressed = await compress_session(
            stored, llm, session_id, _budget_chars(user_id)
        )
        # 안 줄었으면 저장할 이유가 없음. 매 턴 스냅샷을 통째로 쓰면 그 사이 들어온
        # 다음 턴의 메시지가 사라짐 — 압축은 수백 턴에 한 번이고 이 경로는 매 턴임
        if compressed["messages"] != stored["messages"]:
            latest = session.load(session_id)
            latest["messages"] = compressed["messages"]
            latest["archive"] = compressed["archive"]
            session.save(session_id, latest)
            log.info("압축함 session=%s %d→%d개", session_id, len(stored["messages"]), len(compressed["messages"]))
    except Exception:
        log.exception("압축 실패 session=%s", session_id)


def _budget_chars(user_id: str) -> int:
    """압축을 시작할 크기. 모델이 받는 토큰 수에서 비율로 잡음.
    한국어는 1자가 1토큰에 가까워 글자 수를 토큰 상한으로 써도 안전한 과대추정임."""
    window = catalog.context_window(settings.load(user_id)["model"])
    ratio = guide.load(__file__, JOB_FILE).get("compress_start_ratio", 0.6)
    return int(window * ratio) if window else 0
