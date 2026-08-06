"""폴더별 healer_*.json 로더. 서버 재시작 없이 반영되도록 매 호출마다 읽음."""

from __future__ import annotations

import json
from pathlib import Path


def load(module_file: str, name: str) -> dict:
    """module_file과 같은 폴더의 name json을 읽음. 없거나 깨져도 앱은 계속 돎."""
    return _read(Path(module_file).resolve().parent / name)


def load_shared(name: str) -> dict:
    """폴더 여럿이 함께 쓰는 설정. 한쪽에 두고 다른 쪽이 복사하면 조용히 갈라짐."""
    return _read(Path(__file__).resolve().parent / name)


def _read(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}
