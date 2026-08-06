"""이 환경에서 실제로 쓸 수 있는 모델 목록."""

from __future__ import annotations

from algocean_codex_oauth import (
    AlgoceanCodexOAuthError,
    list_models,
    validate_effort,
)

from app.llm import claude

# provider의 chat() 프리셋은 ignore_user_config=True 사용.
# 목록도 같은 값으로 뽑아야 함. False로 뽑으면 실행이 닿지 못하는 모델까지
# 보여주고 백엔드가 400을 냄.
IGNORE_USER_CONFIG = True


def _local_options() -> list[dict]:
    """호스트 로그인으로 도는 모델. codex CLI에서 실시간으로 읽어옴."""
    return [
        {
            "slug": m.slug,
            "name": m.display_name,
            "efforts": list(m.efforts),
            "default_effort": m.default_effort,
        }
        for m in list_models(ignore_user_config=IGNORE_USER_CONFIG)
    ]


def options() -> list[dict]:
    """화면 드롭다운에 뜨는 전부. 키 전용 모델은 키가 있을 때만 낌."""
    return _local_options() + claude.options()


def context_window(model: str) -> int:
    """모델이 받는 토큰 수. 압축 임계를 비율로 잡으려면 이 값이 필요함."""
    if found := claude.spec(model):
        return int(found.get("context_window") or 0)
    for m in list_models(ignore_user_config=IGNORE_USER_CONFIG):
        if m.slug == model:
            return int(m.context_window or 0)
    return 0


def problem(model: str, effort: str) -> str | None:
    """실행 가능한 조합인지 봄. 문제가 있으면 사유를, 없으면 None."""
    if claude.spec(model):
        return claude.problem(model, effort)
    if model not in {m["slug"] for m in _local_options()}:
        return f"모르는 모델입니다: {model}"
    try:
        validate_effort(effort, model=model, ignore_user_config=IGNORE_USER_CONFIG)
    except AlgoceanCodexOAuthError as exc:
        return str(exc)
    return None
