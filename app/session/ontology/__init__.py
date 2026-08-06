"""온톨로지 패키지. 구현은 각 이름 있는 모듈에 있음."""

from app.session.ontology.extract import extract
from app.session.ontology.gate import build_context
from app.session.ontology.retrieve import focus_tags

__all__ = ["build_context", "extract", "focus_tags"]
