import pytest

from trends_agent.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_MODEL_RESEARCH", "OPENAI_MODEL_TRIAGE", "ALLOWED_CHANNEL_IDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_defaults_load_without_env_file() -> None:
    settings = Settings(_env_file=None)
    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.slack_mode == "socket"
    assert settings.slash_response_visibility == "public"
    assert settings.allowed_channel_ids == []


def test_allowed_channel_ids_parsed_from_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_CHANNEL_IDS", "C123, C456 ,")
    settings = Settings(_env_file=None)
    assert settings.allowed_channel_ids == ["C123", "C456"]


def test_missing_api_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ValueError, match="openai_api_key"):
        Settings(_env_file=None)


def test_secrets_are_not_leaked_in_repr() -> None:
    settings = Settings(_env_file=None)
    assert "sk-test" not in repr(settings)


def test_empty_sources_path_means_bundled_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCES_PATH", "")
    assert Settings(_env_file=None).sources_path is None
