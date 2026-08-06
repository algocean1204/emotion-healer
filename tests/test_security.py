"""보안 경계. 뚫리면 감정 기록이 통째로 새는 자리들임."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.auth import store as auth_store
from app.auth import throttle

CONFIG = json.loads(
    (Path(auth_store.__file__).parent / auth_store.CONFIG_FILE).read_text(encoding="utf-8")
)
MAX_FAILURES = CONFIG["throttle"]["max_failures"]


def _login(client, user_id: str, password: str, code: str | None = None):
    """코드를 안 주면 지금 설정된 진짜 코드를 씀. 값이 바뀌어도 테스트가 안 깨짐."""
    return client.post(
        "/api/auth/login",
        json={
            "user_id": user_id,
            "password": password,
            "code": auth_store.invite_code() if code is None else code,
        },
    )


# -- 시도 제한 ---------------------------------------------------------------


def test_repeated_failures_lock_out_even_the_right_password(account) -> None:
    """코드가 이 서비스의 문임. 무제한으로 두드리게 두면 4자리는 하루면 뚫림."""
    with TestClient(main.app) as client:
        for _ in range(MAX_FAILURES):
            assert _login(client, account["user_id"], "틀림").status_code == 401

        blocked = _login(client, account["user_id"], account["password"])

    assert blocked.status_code == 401


def test_lockout_does_not_say_it_is_a_lockout(account) -> None:
    """왜 막혔는지 알려주면 제한을 우회할 타이밍을 알려주는 셈임."""
    with TestClient(main.app) as client:
        first = _login(client, account["user_id"], "틀림")
        for _ in range(MAX_FAILURES):
            _login(client, account["user_id"], "틀림")
        locked = _login(client, account["user_id"], "틀림")

    assert first.status_code == locked.status_code
    assert first.json()["detail"] == locked.json()["detail"]


def test_success_clears_the_counter(account) -> None:
    with TestClient(main.app) as client:
        for _ in range(MAX_FAILURES - 1):
            _login(client, account["user_id"], "틀림")
        assert _login(client, account["user_id"], account["password"]).status_code == 200

        # 성공했으니 다시 실패해도 곧바로 잠기지 않음
        for _ in range(MAX_FAILURES - 1):
            assert _login(client, account["user_id"], "틀림").status_code == 401
        assert _login(client, account["user_id"], account["password"]).status_code == 200


def test_one_locked_id_does_not_lock_another(account) -> None:
    with TestClient(main.app) as client:
        for _ in range(MAX_FAILURES + 1):
            _login(client, "nobodyhere", "틀림")

        assert _login(client, account["user_id"], account["password"]).status_code == 200


# -- 인증코드 ---------------------------------------------------------------


def test_empty_invite_code_lets_nobody_in(account, monkeypatch) -> None:
    """설정 실수로 코드가 비면 문이 열리는 게 아니라 잠겨야 함."""
    monkeypatch.setattr(auth_store, "_config", lambda: {**CONFIG, "verify_code": ""})
    monkeypatch.delenv("HEALER_INVITE_CODE", raising=False)

    with TestClient(main.app) as client:
        assert _login(client, account["user_id"], account["password"], code="").status_code == 401
        assert _login(client, account["user_id"], account["password"]).status_code == 401


def test_env_code_beats_the_file(account, monkeypatch) -> None:
    """컨테이너에서는 파일을 못 고침. 환경변수가 이겨야 함."""
    from_file = CONFIG["verify_code"]
    monkeypatch.setenv("HEALER_INVITE_CODE", "열려라참깨")

    with TestClient(main.app) as client:
        blocked = _login(client, account["user_id"], account["password"], code=from_file)
        ok = _login(client, account["user_id"], account["password"], code="열려라참깨")

    assert blocked.status_code == 401
    assert ok.status_code == 200


# -- 토큰 --------------------------------------------------------------------


def test_token_is_not_stored_in_the_clear(account) -> None:
    """DB가 새도 세션은 못 훔치게. 쿠키의 원문이 DB에 그대로 있으면 안 됨."""
    with TestClient(main.app) as client:
        assert _login(client, account["user_id"], account["password"]).status_code == 200
        cookie = client.cookies.get("healer_token")

    assert cookie
    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT token FROM auth_tokens WHERE user_id = %s", (account["user_id"],))
        stored = [row[0] for row in cursor.fetchall()]

    assert stored
    assert cookie not in stored
    assert auth_store._fingerprint(cookie) in stored


def test_tokens_per_user_are_capped(account) -> None:
    """로그인할 때마다 쌓이면 탈취 표면이 계속 넓어짐."""
    keep = CONFIG["max_tokens_per_user"]
    for _ in range(keep + 3):
        with TestClient(main.app) as client:
            assert _login(client, account["user_id"], account["password"]).status_code == 200
            throttle.reset()

    with auth_store.connect() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM auth_tokens WHERE user_id = %s", (account["user_id"],)
        )
        counted = cursor.fetchone()

    assert counted is not None
    assert counted[0] <= keep


def test_a_made_up_token_gets_nothing(account) -> None:
    with TestClient(main.app) as client:
        client.cookies.set("healer_token", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert client.get("/api/sessions").status_code == 401


# -- 쿠키 --------------------------------------------------------------------


def test_cookie_is_httponly_and_can_be_made_secure(account, monkeypatch) -> None:
    with TestClient(main.app) as client:
        plain = _login(client, account["user_id"], account["password"])
    assert "httponly" in plain.headers["set-cookie"].lower()
    assert "secure" not in plain.headers["set-cookie"].lower()

    monkeypatch.setenv("HEALER_COOKIE_SECURE", "1")
    throttle.reset()
    with TestClient(main.app) as client:
        secured = _login(client, account["user_id"], account["password"])
    assert "secure" in secured.headers["set-cookie"].lower()


# -- 입력 크기 ---------------------------------------------------------------


def test_a_huge_message_is_refused(client, session_id) -> None:
    """상한이 없으면 긴 입력 한 방으로 컨텍스트와 비용이 함께 터짐."""
    from app import guide

    limit = int(guide.load(main.__file__, main.JOB_FILE)["max_message_chars"])
    response = client.post(
        "/api/chat", json={"message": "가" * (limit + 1), "session_id": session_id}
    )

    assert response.status_code == 413


# -- 키 ----------------------------------------------------------------------


def test_no_endpoint_ever_returns_the_api_key(client, monkeypatch) -> None:
    """사용자별 키는 받지 않음. 서버가 든 키 하나가 어디로도 새면 안 됨."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leak")

    seen = " ".join(
        client.get(path).text for path in ("/api/settings", "/api/sessions", "/api/memory")
    )

    assert "sk-ant-must-not-leak" not in seen
