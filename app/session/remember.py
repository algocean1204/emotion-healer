"""턴이 끝난 뒤 기억을 만듦. 압축과 달리 매 턴 돎 — 압축은 수백 턴 뒤에야 걸리는데
기억을 거기에 묶으면 평범한 대화에서는 영원히 비어 있음."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app import guide
from app.session import ontology
from app.session.compress import rules
from app.session.ontology import curator, graph_store
from app.session.ontology import store as ontology_store
from app.session.store import Session

ONTOLOGY_FILE = "healer_ontology.json"


async def remember(session: Session, llm: BaseChatModel, thread_id: str) -> Session:
    """방금 끝난 턴에서 노드를 뽑고, 남은 기억이 있으면 다음 턴에 쓸 배경까지 만듦."""
    sentences = rules.to_sentences(session)
    if not sentences:
        return session

    # 문장 id는 세션 전체 기준이라 노드의 원문 복구 경로가 턴이 쌓여도 어긋나지 않음
    latest_turn = max(sentence["turn_index"] for sentence in sentences)
    fresh = [sentence for sentence in sentences if sentence["turn_index"] == latest_turn]
    # AI 질문은 앞 턴, 답은 이번 턴이라 답만 보면 "그냥 지원이요"가 무슨 말인지 알 수 없음.
    # 앞 턴 AI 발화를 추출 대상이 아니라 문맥으로만 함께 넘김
    context = [
        sentence["text"]
        for sentence in sentences
        if sentence["turn_index"] == latest_turn - 1 and sentence["role"] == "ai"
    ]
    await ontology.extract(thread_id, fresh, llm, context)

    # '그만 말해' 류는 새 노드만 quiet 가 되면 안 됨. 이미 승격된 화제도 내림
    human_text = " ".join(
        sentence["text"] for sentence in fresh if sentence.get("role") == "human"
    )
    # healer_ontology.json 은 ontology 패키지에 있음
    config = guide.load(graph_store.__file__, ONTOLOGY_FILE)
    stop = config.get("disclosure_signals", {}).get("stop", [])
    if human_text and ontology_store.matches_any(human_text, stop):
        graph_store.quiet_proactive(thread_id)

    if not graph_store.has_active(thread_id):
        return session
    return await curator.curate(session, llm, thread_id)
