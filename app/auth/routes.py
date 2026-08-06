"""가입·로그인·로그아웃. 토큰은 HttpOnly 쿠키로만 전달됨 — JS가 읽으면 XSS 한 번에 털림."""

from __future__ import annotations

import os

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth import store, throttle

COOKIE_NAME = "healer_token"
# 아이디·비밀번호·인증코드 중 무엇이 틀렸는지 구분해주지 않음
REJECTED = "아이디 또는 비밀번호가 맞지 않습니다."

router = APIRouter(prefix="/api/auth")


class Credentials(BaseModel):
    user_id: str
    password: str
    code: str


def _cookie_is_secure() -> bool:
    """HTTPS로 올릴 때 켬. 켜면 http에서는 쿠키가 아예 안 실림."""
    return os.getenv("HEALER_COOKIE_SECURE", "") == "1"


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(),
        max_age=store.token_seconds(),
    )


def _client_key(request: Request, user_id: str) -> str:
    """아이디 하나를 노리는 공격과 아이디를 훑는 공격을 둘 다 세야 함."""
    host = request.client.host if request.client else "unknown"
    return f"{host}|{user_id.strip().lower()[:32]}"


def _guard(request: Request, user_id: str) -> str:
    """제한에 걸렸으면 여기서 끝냄. 왜 막혔는지, 언제 풀리는지는 알려주지 않음."""
    key = _client_key(request, user_id)
    if throttle.is_locked(key):
        raise HTTPException(status_code=401, detail=REJECTED)
    return key


@router.post("/register")
async def register(req: Credentials, request: Request, response: Response) -> dict:
    key = _guard(request, req.user_id)
    if not store.code_matches(req.code):
        throttle.record_failure(key)
        raise HTTPException(status_code=401, detail=REJECTED)
    if reason := store.problem(req.user_id, req.password):
        raise HTTPException(status_code=400, detail=reason)
    if not store.create_user(req.user_id, req.password):
        raise HTTPException(status_code=409, detail="이미 있는 아이디입니다.")
    throttle.clear(key)
    _set_cookie(response, store.issue_token(req.user_id))
    return {"user_id": req.user_id}


@router.post("/login")
async def login(req: Credentials, request: Request, response: Response) -> dict:
    key = _guard(request, req.user_id)
    # 코드가 틀렸는지 비밀번호가 틀렸는지 응답으로 구분되면 안 되므로 한 갈래로 묶음
    if not store.code_matches(req.code) or not store.verify_password(req.user_id, req.password):
        throttle.record_failure(key)
        raise HTTPException(status_code=401, detail=REJECTED)
    throttle.clear(key)
    store.sweep_expired()
    _set_cookie(response, store.issue_token(req.user_id))
    return {"user_id": req.user_id}


@router.post("/logout")
async def logout(response: Response, healer_token: str = Cookie(default="")) -> dict:
    store.revoke_token(healer_token)
    response.delete_cookie(COOKIE_NAME)
    return {}


@router.get("/me")
async def me(healer_token: str = Cookie(default="")) -> dict:
    user_id = store.user_for_token(healer_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {"user_id": user_id}


def current_user(healer_token: str = Cookie(default="")) -> str:
    """보호가 필요한 모든 엔드포인트가 이걸 의존성으로 씀."""
    user_id = store.user_for_token(healer_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user_id
