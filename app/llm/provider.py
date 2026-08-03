"""쓸 모델을 만든다. app/llm 밖에서는 벤더 이름이 나오지 않는다."""

from __future__ import annotations

from algocean_codex_oauth import AlgoceanCodexOAuth
from algocean_codex_oauth.auth_mode import resolve_auth_from_env
from langchain_core.language_models import BaseChatModel

from app import settings


def get_chat_model() -> BaseChatModel:
    """설정 파일의 모델과 effort로 만든다.

    로컬 Codex 로그인과 배포용 API 키 중 무엇을 쓸지는 라이브러리가 환경에서
    판단한다. ALGOCEANCODEXOAUTH_API 가 있으면 키 모드, 없으면 로그인 모드다.
    """
    cfg = settings.load()
    return AlgoceanCodexOAuth.chat(
        model=cfg["model"],
        reasoning_effort=cfg["effort"],
        auth=resolve_auth_from_env(),
    )
