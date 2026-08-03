"""벤더 이름이 등장하는 유일한 파일."""

from __future__ import annotations

import os

from algocean_codex_oauth import AlgoceanCodexOAuth, api_key, oauth
from langchain_core.language_models import BaseChatModel

DEFAULT_MODEL = "gpt-5.5"


def get_chat_model() -> BaseChatModel:
    """환경변수로 로컬(OAuth)과 배포(API 키)를 가른다."""
    auth = api_key if os.getenv("ALGOCEANCODEXOAUTH_AUTH") == "api_key" else oauth
    return AlgoceanCodexOAuth.chat(
        model=os.getenv("EMOTION_HEALER_MODEL", DEFAULT_MODEL),
        auth=auth,
    )
