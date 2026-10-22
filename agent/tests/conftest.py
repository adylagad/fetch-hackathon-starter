import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SEED_PHRASE", "hackkit showcase smoke test seed phrase only")
    monkeypatch.delenv("AGENTVERSE_API_KEY", raising=False)
