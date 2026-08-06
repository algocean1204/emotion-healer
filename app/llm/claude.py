"""API 키로만 도는 백엔드. 로컬 로그인 경로는 없음.

떼어낼 때 만질 곳은 넷임 — 이 파일, `healer_claude.json`, `provider.py` 와
`catalog.py` 의 `claude` 참조, `pyproject.toml` 의 `langchain-anthropic`.
"""

from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from app import guide

CONFIG_FILE = "healer_claude.json"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def api_key() -> str:
    """키는 서버 환경변수 한 곳에만 있음. 설정 파일에도 DB에도 두지 않음."""
    return os.getenv(_config().get("env_key", ""), "")


def options() -> list[dict]:
    """키가 없으면 빈 목록. 못 쓰는 모델을 보여주면 골랐다가 실패함."""
    if not api_key():
        return []
    return [
        {
            "slug": model["slug"],
            "name": model["name"],
            "efforts": list(model["efforts"]),
            "default_effort": model["default_effort"],
        }
        for model in _config().get("models", [])
    ]


def spec(model: str) -> dict | None:
    """이 백엔드가 아는 모델인지. 모르면 None 이라 호출부가 다른 백엔드로 넘어감."""
    for candidate in _config().get("models", []):
        if candidate["slug"] == model:
            return candidate
    return None


def problem(model: str, effort: str) -> str | None:
    """고른 조합이 실행 가능한지. 문제가 있으면 사유를, 없으면 None."""
    if not api_key():
        return f"{model}을(를) 쓰려면 서버에 API 키가 필요합니다."
    found = spec(model)
    if found is None:
        return f"모르는 모델입니다: {model}"
    if effort not in found["efforts"]:
        return f"{model}이(가) 받지 않는 강도입니다: {effort}"
    return None


def build(model: str, effort: str) -> ChatAnthropic:
    """effort 는 사고 길이 스위치. 활성화 시 길이는 모델이 결정함.

    timeout 을 None 으로 넘기면 SDK 기본값(600초)까지 덮여 무한 대기가 됨.
    한 번 매달리면 그 세션의 잡이 running 에 갇혀 다음 메시지가 전부 막히므로
    실수치를 반드시 넘김.
    """
    config = _config()
    thinking = {"type": "adaptive"} if effort == config.get("thinking_effort") else None
    return ChatAnthropic(
        model_name=model,
        thinking=thinking,
        api_key=SecretStr(api_key()),
        timeout=float(config.get("timeout_seconds", 120)),
        max_retries=int(config.get("max_retries", 1)),
        stop=None,
    )
