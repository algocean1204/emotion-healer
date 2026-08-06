"""쓸 모델을 만듦. app/llm 밖에서는 벤더 이름이 나오지 않음."""

from __future__ import annotations

from algocean_codex_oauth import AlgoceanCodexOAuth
from algocean_codex_oauth.auth_mode import resolve_auth_from_env
from langchain_core.language_models import BaseChatModel

from app import settings
from app.llm import claude
from app.settings.store import Settings


def get_chat_model(cfg: Settings | None = None, user_id: str | None = None) -> BaseChatModel:
    """설정으로 모델을 만듦. user_id 가 있으면 그 사람 Postgres 설정을 읽음.

    사용자 API 키는 받지 않음 — 서버 env / 호스트 OAuth 만.
    """
    if cfg is None:
        cfg = settings.load(user_id)
    if claude.spec(cfg["model"]):
        return claude.build(cfg["model"], cfg["effort"])
    return AlgoceanCodexOAuth.chat(
        model=cfg["model"],
        reasoning_effort=cfg["effort"],
        auth=resolve_auth_from_env(),
    )
