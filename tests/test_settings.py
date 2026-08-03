"""설정 파일 읽기·쓰기. codex CLI를 타지 않는다."""

import json

from app import settings


def test_defaults_when_file_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "PATH", tmp_path / "없는파일.json")
    assert settings.load() == {"model": "gpt-5.6-luna", "effort": "max"}


def test_defaults_when_file_broken(tmp_path, monkeypatch) -> None:
    path = tmp_path / "healer-setting.json"
    path.write_text("{ 깨진 json", encoding="utf-8")
    monkeypatch.setattr(settings, "PATH", path)
    # 설정이 망가져도 앱은 떠야 한다
    assert settings.load() == settings.defaults()


def test_save_then_load(tmp_path, monkeypatch) -> None:
    path = tmp_path / "healer-setting.json"
    monkeypatch.setattr(settings, "PATH", path)

    settings.save({"model": "gpt-5.5", "effort": "high"})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "model": "gpt-5.5",
        "effort": "high",
    }
    assert settings.load() == {"model": "gpt-5.5", "effort": "high"}
