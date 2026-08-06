"""턴 시작 주입 게이트. quiet 노드의 원문은 여기서 절대 새지 않음. LLM을 부르지 않음."""

from __future__ import annotations

from app import guide
from app.session.ontology import graph_store
from app.session.ontology import memory_pack
from app.session.ontology.identity import identity_lines
from app.session.ontology.retrieve import cap_resident, focus_tags, matches_focus
from app.session.store import Session

CONFIG_FILE = "healer_ontology.json"


def _config() -> dict:
    return guide.load(__file__, CONFIG_FILE)


def _tone_lines(quiet_nodes: list[dict], config: dict) -> list[str]:
    """quiet 노드는 원문 대신 태그 하나짜리 톤 문장으로만 존재를 알림.

    노드 수는 resident_limit이 잡지만 태그는 노드당 서너 개씩 붙음. 실측에서 다섯
    노드가 톤 문장 열다섯 줄이 됐다 — 배경이 사용자 발화보다 길어지는 자리라 여기서 끊음.
    """
    template = config.get("tone_line_template", "{tag} 화제엔 조심스럽게")
    tags = dict.fromkeys(tag for node in quiet_nodes for tag in node["tags"])
    limit = config.get("tone_line_limit", 5)
    return [template.format(tag=tag) for tag in list(tags)[:limit]]


def build_context(session: Session, user_message: str, thread_id: str) -> str:
    """이번 턴 프롬프트에 넣을 배경 문자열. 결과가 없으면 빈 문자열."""
    # 민감 정보는 어떤 경로로도 원문이 안 나감. 위기 노드만 예외로 남김 —
    # 학대 기록은 sensitivity가 붙지만 안전 판단에 필요함
    active = [
        node
        for node in graph_store.nodes(thread_id)
        if (
            node["status"] == "active"
            and node.get("origin", "user") == "user"
            and (not node.get("sensitivity") or node.get("crisis"))
        )
    ]
    crisis_nodes = [node for node in active if node.get("crisis")]
    proactive_nodes = [node for node in active if node.get("disclosure") == "proactive" and not node.get("crisis")]

    config = _config()
    # 톤 문장은 노드마다 태그 수만큼 늘어남. 상한을 안 걸면 프롬프트를 조용히 잡아먹음
    quiet_nodes = cap_resident(
        [node for node in active if node.get("disclosure", "quiet") != "proactive" and not node.get("crisis")],
        config.get("resident_limit", 5),
    )

    # session["memory"]는 큐레이터 몫임. 없거나 비어 있으면 태그 매칭으로 떨어짐.
    # 후보는 id만 받아 쓰고 실물은 지금 노드에서 다시 집음 — 사본은 그 뒤의 지움·잠금을 모름
    memory = session.get("memory") or {}
    live = {node["id"]: node for node in active}
    cached_ids = memory_pack.candidate_ids(memory) if memory_pack.is_fresh(memory) else []
    # 캐시 후보는 id 만 믿고 live 로 다시 집음 — 지움·민감 필터를 지난 것만 삼
    candidate_pool = [live[node_id] for node_id in cached_ids if node_id in live] if cached_ids else quiet_nodes
    # tone_lines 사본은 민감 태그를 실을 수 있어, 후보가 live 로 줄었으면 다시 만듦
    tone_source = (
        memory.get("tone_lines")
        if cached_ids and len(candidate_pool) == len(cached_ids)
        else None
    ) or _tone_lines(quiet_nodes, config)

    # 조용한 기억은 이번 발화에서 사용자가 다시 꺼낸 화제에만 공개.
    # 가진 노드를 같이 넘겨야 별칭 사전 밖 화제(잠·이직·친구)도 열림
    opened = focus_tags(user_message, active)
    session["opened_topics"] = opened
    opened_nodes = [node for node in candidate_pool if matches_focus(node, opened)]

    raw_nodes = {node["id"]: node for node in [*crisis_nodes, *proactive_nodes, *opened_nodes]}
    # 정체성은 맨 앞. main 이 미리 뽑은 줄을 넘기면 DB 재조회 없이 씀
    identity = identity_lines(thread_id)
    fact_lines = [f"{node['subject']} {node['predicate']} {node['object']}." for node in raw_nodes.values()]
    lines = [*identity, *tone_source, *fact_lines]
    return " ".join(lines)
