"""태그 필터와 상주 상한. LLM도 DB도 타지 않는 순수 판정만 둠."""

from __future__ import annotations

from app import guide
from app.session.ontology import store as ontology_store

CONFIG_FILE = "healer_ontology.json"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def focus_tags(text: str, nodes: list[dict] | None = None) -> list[str]:
    """이번 발화가 어떤 화제를 열었는지. 별칭 사전 + 가진 노드의 subject·tags를 봄.

    사전만 보면 다섯 개(엄마·아빠·회사·직장 상사·팀장님) 밖의 화제는 어떤 기억도
    못 꺼냄. 실제로 쌓이는 노드는 `잠`·`이직`·`친구`처럼 사전에 없는 말이 대부분임.
    """
    aliases = _config().get("aliases", {})
    hits: list[str] = []

    def add(word: str) -> None:
        if word and word in text and word not in hits:
            hits.append(word)

    for phrase, canonical in aliases.items():
        if phrase in text and canonical not in hits:
            hits.append(canonical)
    for canonical in dict.fromkeys(aliases.values()):
        add(canonical)
    for node in nodes or []:
        add(node.get("subject", ""))
        for tag in node.get("tags", []):
            add(str(tag))
    return hits


def matches_focus(node: dict, focus: list[str]) -> bool:
    return node["subject"] in focus or any(tag in focus for tag in node["tags"])


def cap_resident(nodes: list[dict], limit: int) -> list[dict]:
    """상주 상한을 적용함. 위기 신호 노드는 상한 밖이라 밀려나지 않음."""
    config = _config()
    crisis = [node for node in nodes if node.get("crisis")]
    rest = sorted(
        (node for node in nodes if not node.get("crisis")),
        key=lambda node: ontology_store.decayed_salience(node, config),
        reverse=True,
    )
    remaining = max(limit - len(crisis), 0)
    return crisis + rest[:remaining]
