"""사용자와 로그인 토큰. 비밀번호 원문은 어디에도 남기지 않음.

지인 테스트용 최소 인증이라 기능은 적지만, 비밀번호 해시와 상수 시간 비교는 유지.
여기를 줄이면 DB 한 번 새는 순간 전부 털림.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import psycopg

from app import guide

CONFIG_FILE = "healer_auth.json"
DEFAULT_DSN = "postgresql://healer:healer@localhost:5432/healer"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def dsn() -> str:
    return os.getenv("POSTGRES_DSN", DEFAULT_DSN)


def connect() -> psycopg.Connection:
    return psycopg.connect(dsn())


def problem(user_id: str, password: str) -> str:
    """가입 입력이 규칙에 안 맞으면 그 이유를, 맞으면 빈 문자열."""
    config = _config()
    if not re.match(config.get("user_id_pattern", "^.+$"), user_id):
        return "아이디는 영문 소문자·숫자·밑줄 3~20자입니다."
    if len(password) < config.get("password_min_length", 4):
        return f"비밀번호는 {config.get('password_min_length', 4)}자 이상이어야 합니다."
    return ""


def token_seconds() -> int:
    return int(_config().get("token_days", 30)) * 86400


def invite_code() -> str:
    """환경변수가 이김. 컨테이너에서는 파일을 고칠 수 없기 때문.

    파일 쪽(`healer_auth.json`)은 gitignore 대상이라 저장소에 안 남음.
    """
    return os.getenv("HEALER_INVITE_CODE") or str(_config().get("verify_code", ""))


def code_matches(code: str) -> bool:
    """인증코드 비교. 짧아도 상수 시간으로 봄.

    코드가 비어 있으면 아무것도 통과시키지 않음 — 설정 실수로 문이 열리면 안 됨.
    """
    expected = invite_code()
    if not expected:
        return False
    # str 끼리 비교하면 비ASCII 코드에서 TypeError 가 남. 한글 코드도 쓸 수 있어야 함
    return hmac.compare_digest(code.strip().encode("utf-8"), expected.encode("utf-8"))


def _hash(password: str, salt: bytes) -> str:
    scrypt = _config().get("scrypt", {})
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=scrypt.get("n", 16384),
        r=scrypt.get("r", 8),
        p=scrypt.get("p", 1),
    )
    return derived.hex()


def create_user(user_id: str, password: str) -> bool:
    """이미 있는 아이디면 False. 있는지 먼저 묻지 않고 제약에 맡김(경합 없음)."""
    salt = secrets.token_bytes(16)
    with connect() as db, db.cursor() as cursor:
        try:
            cursor.execute(
                "INSERT INTO users (user_id, password_hash, password_salt) VALUES (%s, %s, %s)",
                (user_id, _hash(password, salt), salt.hex()),
            )
        except psycopg.errors.UniqueViolation:
            return False
    return True


def verify_password(user_id: str, password: str) -> bool:
    with connect() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT password_hash, password_salt FROM users WHERE user_id = %s", (user_id,)
        )
        row = cursor.fetchone()
    if row is None:
        # 없는 아이디도 해시를 한 번 돌림. 응답 시간으로 계정 존재를 알 수 없게
        _hash(password, secrets.token_bytes(16))
        return False
    return hmac.compare_digest(_hash(password, bytes.fromhex(row[1])), row[0])


def _fingerprint(token: str) -> str:
    """DB에는 지문만 남김. 원문은 쿠키에만 있어서 DB가 새도 세션은 못 훔침.

    토큰은 이미 128비트 난수라 솔트나 느린 해시가 필요 없음 — 사전 공격 대상이 아님.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=_config().get("token_days", 30))
    keep = int(_config().get("max_tokens_per_user", 10))
    with connect() as db, db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (_fingerprint(token), user_id, expires),
        )
        # 로그인할 때마다 토큰이 쌓임. 오래된 것부터 잘라 탈취 표면을 줄임
        cursor.execute(
            "DELETE FROM auth_tokens WHERE user_id = %s AND token NOT IN ("
            "  SELECT token FROM auth_tokens WHERE user_id = %s"
            "  ORDER BY created_at DESC LIMIT %s)",
            (user_id, user_id, keep),
        )
    return token


def user_for_token(token: str) -> str | None:
    """만료된 토큰은 없는 것으로 봄. 정리는 다음 로그인 때 함께 함."""
    if not token:
        return None
    with connect() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM auth_tokens WHERE token = %s AND expires_at > now()",
            (_fingerprint(token),),
        )
        row = cursor.fetchone()
    return row[0] if row else None


def revoke_token(token: str) -> None:
    if not token:
        return
    with connect() as db, db.cursor() as cursor:
        cursor.execute("DELETE FROM auth_tokens WHERE token = %s", (_fingerprint(token),))


def sweep_expired() -> None:
    with connect() as db, db.cursor() as cursor:
        cursor.execute("DELETE FROM auth_tokens WHERE expires_at <= now()")
