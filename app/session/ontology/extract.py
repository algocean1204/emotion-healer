"""온톨로지 추출. 사실은 생기는 순간에 잡아야 해서 턴이 끝날 때마다 그 턴 문장에서 뽑음."""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel

from app import guide
from app.session.ontology import graph_store, prompt, schema
from app.session.ontology import store as ontology_store

CONFIG_FILE = "healer_ontology.json"


def _parse_json(raw: str) -> dict:
    text = raw.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def extract(
    thread_id: str, candidates: list[dict], llm: BaseChatModel, context: list[str] | None = None
) -> None:
    """건네받은 문장에서 노드를 뽑아 그래프에 넣음. 기존 노드는 덮지 않음.

    context는 앞 턴 AI 발화. 노드로 추출하지 않고 짧은 답의 의미 해석에만 사용.
    """
    if not candidates:
        return
    sentence_by_id = {sentence["id"]: sentence for sentence in candidates}

    active_nodes = [node for node in graph_store.nodes(thread_id) if node["status"] == "active"]
    ai = await llm.ainvoke(prompt.extract_request(candidates, active_nodes, context or []))
    parsed = _parse_json(str(ai.content))
    config = guide.load(__file__, CONFIG_FILE)
    aliases = config.get("aliases", {})

    built: list[dict] = []
    built_index_by_raw_index: dict[int, int] = {}
    for raw_index, raw_node in enumerate(parsed.get("nodes", []) or []):
        if not isinstance(raw_node, dict) or raw_node.get("origin", "user") != "user":
            continue
        raw_source_ids = raw_node.get("source_ids", [])
        if not isinstance(raw_source_ids, list):
            continue
        source_ids = [
            sid
            for sid in raw_source_ids
            if isinstance(sid, str) and sid in sentence_by_id and sentence_by_id[sid].get("role") == "human"
        ]
        if not source_ids:
            continue
        node = schema.build(raw_node, thread_id, source_ids)
        if node is None:
            continue
        source_text = " ".join(sentence_by_id[sid]["text"] for sid in source_ids)
        node["disclosure"] = ontology_store.classify_disclosure(source_text, node["origin"], config)
        built_index_by_raw_index[raw_index] = len(built)
        built.append(ontology_store.normalize(node, aliases))

    supersedes: dict[str, str] = {}
    raw_supersedes = parsed.get("supersedes", {})
    for old_id, raw_index in (raw_supersedes.items() if isinstance(raw_supersedes, dict) else []):
        if isinstance(old_id, str) and isinstance(raw_index, int) and raw_index in built_index_by_raw_index:
            supersedes[old_id] = built[built_index_by_raw_index[raw_index]]["id"]

    graph_store.add(thread_id, built, supersedes)
