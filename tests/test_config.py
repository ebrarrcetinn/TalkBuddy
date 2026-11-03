# Ayarların .env'den doğru okunduğunu ve eksik anahtarın yakalandığını test eder.
import pytest

from app.config import load_settings


def test_reads_key_and_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  test-key  ")
    monkeypatch.setenv("COACH_MODEL", "test-model")

    settings = load_settings()

    assert settings.anthropic_api_key == "test-key"
    assert settings.coach_model == "test-model"


def test_uses_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("COACH_MODEL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    settings = load_settings()

    assert settings.coach_model == "claude-sonnet-5-5"
    assert settings.database_path == "talkbuddy.db"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_rejects_missing_or_empty_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        load_settings()
