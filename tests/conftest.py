import pytest

from trends_agent.config import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return Settings(_env_file=None, session_db_path=":memory:", agent_timeout_seconds=0.2)
