"""이 환경에서 실제로 쓸 수 있는 모델 목록."""

from __future__ import annotations

from algocean_codex_oauth import (
    AlgoceanCodexOAuthError,
    list_models,
    validate_effort,
)

# provider가 chat() 프리셋으로 돌고 그 프리셋이 ignore_user_config=True다.
# 목록도 같은 값으로 뽑아야 한다. False로 뽑으면 실행이 닿지 못하는 모델까지
# 보여주고 백엔드가 400을 낸다.
IGNORE_USER_CONFIG = True


def options() -> list[dict]:
    """모델과 각 모델이 받는 effort 목록. codex CLI에서 실시간으로 읽어온다."""
    return [
        {
            "slug": m.slug,
            "name": m.display_name,
            "efforts": list(m.efforts),
            "default_effort": m.default_effort,
        }
        for m in list_models(ignore_user_config=IGNORE_USER_CONFIG)
    ]


def problem(model: str, effort: str) -> str | None:
    """실행 가능한 조합인지 본다. 문제가 있으면 사유를, 없으면 None."""
    if model not in {m["slug"] for m in options()}:
        return f"모르는 모델입니다: {model}"
    try:
        validate_effort(effort, model=model, ignore_user_config=IGNORE_USER_CONFIG)
    except AlgoceanCodexOAuthError as exc:
        return str(exc)
    return None
