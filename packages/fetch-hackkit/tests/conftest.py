from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest


class FakeStorage:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def has(self, key: str) -> bool:
        return key in self.data

    def remove(self, key: str) -> None:
        self.data.pop(key, None)


class FakeCtx:
    """Just enough of uagents.Context for handler tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []
        self.storage = FakeStorage()
        self.logger = logging.getLogger("test")
        self.session = uuid4()

    async def send(self, destination: str, message: Any) -> None:
        self.sent.append((destination, message))


@pytest.fixture
def ctx() -> FakeCtx:
    return FakeCtx()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SEED_PHRASE", "fetch hackkit unit test seed phrase do not use")
    monkeypatch.delenv("AGENTVERSE_API_KEY", raising=False)
    monkeypatch.delenv("FET_NETWORK", raising=False)
