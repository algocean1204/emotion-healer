"""로그인·가입 시도 제한. 인증코드가 문이니 그 문을 두드리는 횟수를 셈.

워커가 하나라 메모리에 둠. 프로세스를 재시작하면 초기화되는데, 재시작을
공격자가 시킬 수 없으므로 지인 규모에 맞는 크기.
"""

from __future__ import annotations

import time
from collections import defaultdict

from app import guide

CONFIG_FILE = "healer_auth.json"

# key -> 실패한 시각들. 성공하면 지움
_failures: dict[str, list[float]] = defaultdict(list)


def _limits() -> tuple[int, float]:
    config = guide.load(__file__, CONFIG_FILE).get("throttle", {})
    return int(config.get("max_failures", 10)), float(config.get("window_seconds", 300))


def _recent(key: str, window: float, now: float) -> list[float]:
    kept = [at for at in _failures[key] if now - at < window]
    _failures[key] = kept
    return kept


def is_locked(key: str) -> bool:
    """제한 여부 확인. 남은 시간은 공격자에게도 정보라 비공개."""
    max_failures, window = _limits()
    return len(_recent(key, window, time.monotonic())) >= max_failures


def record_failure(key: str) -> None:
    max_failures, window = _limits()
    now = time.monotonic()
    _recent(key, window, now).append(now)
    # 창 밖 기록까지 들고 있을 이유가 없음
    _failures[key] = _failures[key][-max_failures:]


def clear(key: str) -> None:
    """성공하면 그 키의 실패 기록은 의미가 없음."""
    _failures.pop(key, None)


def reset() -> None:
    """테스트가 서로의 상태를 물려받지 않게 함."""
    _failures.clear()
