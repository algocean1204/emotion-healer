"""키 전용 백엔드. 네트워크도 codex CLI도 타지 않음."""

import json
from pathlib import Path

from app.llm import catalog, claude, provider
from app.settings import store

CONFIG = json.loads(
    (Path(claude.__file__).parent / claude.CONFIG_FILE).read_text(encoding="utf-8")
)
SLUG = CONFIG["models"][0]["slug"]
ENV_KEY = CONFIG["env_key"]


def test_no_key_means_no_options(monkeypatch) -> None:
    """키가 없으면 목록에 안 뜸. 못 쓰는 걸 보여주면 골랐다가 실패함."""
    monkeypatch.delenv(ENV_KEY, raising=False)
    assert claude.options() == []


def test_key_puts_model_in_options(monkeypatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-ant-test")
    assert SLUG in {option["slug"] for option in claude.options()}


def test_spec_does_not_depend_on_key(monkeypatch) -> None:
    """소유 판정은 키와 무관. 키 누락 시 codex 경로로의 이탈 차단."""
    monkeypatch.delenv(ENV_KEY, raising=False)
    assert claude.spec(SLUG) is not None
    assert claude.spec("gpt-5.6-luna") is None


def test_problem_names_the_missing_key(monkeypatch) -> None:
    monkeypatch.delenv(ENV_KEY, raising=False)
    reason = claude.problem(SLUG, "adaptive")
    assert reason is not None and "API 키" in reason


def test_problem_rejects_unknown_effort(monkeypatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-ant-test")
    assert claude.problem(SLUG, "xhigh") is not None
    assert claude.problem(SLUG, "adaptive") is None


def test_effort_switches_thinking(monkeypatch) -> None:
    """effort 는 이 백엔드의 사고 길이 스위치."""
    monkeypatch.setenv(ENV_KEY, "sk-ant-test")
    assert claude.build(SLUG, "adaptive").thinking == {"type": "adaptive"}
    assert claude.build(SLUG, "off").thinking is None


def test_key_never_leaves_the_env(monkeypatch) -> None:
    """옵션 어디에도 키가 실리면 안 됨. 이 목록은 화면으로 나감."""
    monkeypatch.setenv(ENV_KEY, "sk-ant-secret")
    assert "sk-ant-secret" not in json.dumps(claude.options(), ensure_ascii=False)


def test_provider_picks_the_key_backend(monkeypatch) -> None:
    """슬러그로 갈림. 이 경로는 codex CLI 를 건드리지 않음."""
    monkeypatch.setenv(ENV_KEY, "sk-ant-test")
    cfg = {"model": SLUG, "effort": "adaptive"}
    assert type(provider.get_chat_model(cfg)).__name__ == "ChatAnthropic"  # type: ignore[arg-type]


def test_catalog_reads_window_from_json(monkeypatch) -> None:
    """압축 임계가 이 값을 씀. 여기서 0 이 나오면 압축이 통째로 어긋남."""
    monkeypatch.setenv(ENV_KEY, "sk-ant-test")
    assert catalog.context_window(SLUG) == CONFIG["models"][0]["context_window"]


def test_catalog_forwards_the_key_backend_reason(monkeypatch) -> None:
    monkeypatch.delenv(ENV_KEY, raising=False)
    reason = catalog.problem(SLUG, "adaptive")
    assert reason is not None and "API 키" in reason
