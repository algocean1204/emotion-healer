"""외부 저장소 둘에 의존함 — 온톨로지는 그래프 DB, 사용자는 관계형 DB."""

from __future__ import annotations

import secrets
from typing import Any, Optional

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.auth import store as auth_store
from app.auth import throttle
from app.session.ontology import graph_store

GRAPH_HINT = "온톨로지 DB가 필요합니다. `NEO4J_PASSWORD=... docker compose up -d db` 후 다시 돌리세요."
USERS_HINT = "사용자 DB가 필요합니다. `POSTGRES_PASSWORD=... docker compose up -d users` 후 다시 돌리세요."


@pytest.fixture(scope="session", autouse=True)
def graph_db():
    try:
        graph_store.driver().verify_connectivity()
    except Exception as exc:
        pytest.exit(f"{GRAPH_HINT}\n원인: {type(exc).__name__}: {exc}", returncode=1)
    yield
    graph_store.close()


@pytest.fixture(scope="session", autouse=True)
def users_db():
    try:
        auth_store.connect().close()
    except Exception as exc:
        pytest.exit(f"{USERS_HINT}\n원인: {type(exc).__name__}: {exc}", returncode=1)


@pytest.fixture(autouse=True)
def fresh_throttle():
    """시도 제한은 프로세스 메모리에 있음. 테스트끼리 물려받으면 안 됨."""
    throttle.reset()
    yield
    throttle.reset()


@pytest.fixture
def thread(request):
    """정체성 격리 단위. 온톨로지 키인 user_id 자리."""
    thread_id = f"test-{request.node.name}"[:120]
    _wipe(thread_id)
    yield thread_id
    _wipe(thread_id)


class SilentModel(BaseChatModel):
    """아무것도 안 뽑는 추출기. 턴 뒤 배경 작업이 진짜 모델을 부르는 걸 막음."""

    @property
    def _llm_type(self) -> str:
        return "silent"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='{"nodes": []}'))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages)


@pytest.fixture
def account():
    """테스트마다 새 사용자. 아이디 규칙(영소문자·숫자·밑줄 3~20자)을 지켜야 함."""
    user_id = "t" + secrets.token_hex(6)
    password = "test1234"
    assert auth_store.create_user(user_id, password)
    yield {"user_id": user_id, "password": password}
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
    _wipe(user_id)


@pytest.fixture
def client(account, tmp_path, monkeypatch):
    """로그인까지 끝난 클라이언트. 세션 파일은 테스트마다 격리된 폴더에 씀."""
    from fastapi.testclient import TestClient

    import app.main as main
    from app.session import store as session_store

    monkeypatch.setattr(session_store, "DIRECTORY", tmp_path)
    # 턴 종료 뒤 기억·압축 실행. 여길 안 막으면 테스트가 실제 모델을 부름
    silent = SilentModel()

    def runtime_with_stub(_user_id: str):
        # graph fixture 가 스텁을 끼워 두면 그걸 쓰고, 없으면 침묵 모델로 조립
        graph = getattr(main, "graph", None)
        if graph is None:
            from app.graph import build_graph

            graph = build_graph(silent)
        return silent, graph

    monkeypatch.setattr(main, "_runtime", runtime_with_stub)
    monkeypatch.setattr(main, "_runtime_cache", {})
    with TestClient(main.app) as testclient:
        response = testclient.post(
            "/api/auth/login",
            json={
                "user_id": account["user_id"],
                "password": account["password"],
                "code": auth_store.invite_code(),
            },
        )
        assert response.status_code == 200, response.text
        testclient.user_id = account["user_id"]  # type: ignore[attr-defined]
        yield testclient


@pytest.fixture
def session_id(client):
    """빈 대화 하나를 만들어 그 id를 줌."""
    response = client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _wipe(key: str) -> None:
    with graph_store.db_session() as db:
        db.run("MATCH (n) WHERE n.thread_id = $key DETACH DELETE n", key=key)
