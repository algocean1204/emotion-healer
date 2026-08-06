"""위기 신호 판정 한 곳. 되묻기와 압축이 같은 규칙을 봐야 한 쪽만 새지 않음."""

from __future__ import annotations

CRISIS_FILE = "healer_crisis.json"


def _squeeze(text: str) -> str:
    """공백을 지우고 봄. `죽고 싶어`만 목록에 있으면 `죽고싶어`가 통째로 빠지는데,
    채팅에서는 붙여 쓰는 형태가 더 흔함."""
    return "".join(text.split())


def has_signal(text: str, keywords: list[str]) -> bool:
    squeezed = _squeeze(text)
    return any(_squeeze(keyword) in squeezed for keyword in keywords)
