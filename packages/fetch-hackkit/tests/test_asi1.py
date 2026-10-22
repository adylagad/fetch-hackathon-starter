from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fetch_hackkit.asi1 import ASI1, ASI1Error, history, remember, tool
from pydantic import BaseModel


def get_weather(city: str, unit: str = "C") -> str:
    """Current weather for a city.

    Args:
        city: City name, e.g. Berkeley.
        unit: C or F.
    """
    return f"18{unit} in {city}"


async def flaky(x: int) -> int:
    """Always fails."""
    raise ValueError("upstream down")


def test_tool_schema_from_signature_and_docstring() -> None:
    t = tool(get_weather)
    assert t.name == "get_weather"
    assert t.description == "Current weather for a city."
    assert t.parameters["required"] == ["city"]
    assert t.parameters["properties"]["city"] == {
        "type": "string",
        "description": "City name, e.g. Berkeley.",
    }
    assert t.parameters["properties"]["unit"]["default"] == "C"
    assert t.spec()["type"] == "function"


async def test_tool_call_validates_and_runs_sync_functions() -> None:
    assert await tool(get_weather).call({"city": "Paris"}) == "18C in Paris"


def _completion(content: str | None = None, tool_calls: list[Any] | None = None) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _call(id: str, name: str, args: dict) -> Any:
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeOpenAI:
    """Replays scripted completions and records every request."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.responses.pop(0)


async def test_run_tools_loop_feeds_results_and_errors_back() -> None:
    fake = FakeOpenAI(
        _completion(
            tool_calls=[
                _call("1", "get_weather", {"city": "Berkeley"}),
                _call("2", "flaky", {"x": 1}),
            ]
        ),
        _completion("It is 18C in Berkeley."),
    )
    calls: list[str] = []
    llm = ASI1(client=fake)  # type: ignore[arg-type]
    answer = await llm.run_tools(
        "weather?",
        [get_weather, flaky],
        system="be brief",
        on_call=lambda name, args, result: calls.append(name),
    )
    assert answer == "It is 18C in Berkeley."
    assert calls == ["get_weather", "flaky"]
    second = fake.requests[1]["messages"]
    assert second[0] == {"role": "system", "content": "be brief"}
    assert second[2]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert second[3] == {"role": "tool", "tool_call_id": "1", "content": "18C in Berkeley"}
    assert "upstream down" in second[4]["content"]


async def test_run_tools_stops_after_max_steps() -> None:
    loop_call = _completion(tool_calls=[_call("1", "get_weather", {"city": "X"})])
    fake = FakeOpenAI(loop_call, loop_call, _completion("best effort"))
    answer = await ASI1(client=fake).run_tools("q", [get_weather], max_steps=2)  # type: ignore[arg-type]
    assert answer == "best effort"
    assert "Stop calling tools" in fake.requests[-1]["messages"][-1]["content"]


class Idea(BaseModel):
    title: str
    score: int


async def test_structured_extracts_and_repairs() -> None:
    fake = FakeOpenAI(
        _completion('Sure! ```json\n{"title": "x"}\n```'),
        _completion('{"title": "Agent", "score": 9}'),
    )
    idea = await ASI1(client=fake).structured("idea", Idea)  # type: ignore[arg-type]
    assert idea == Idea(title="Agent", score=9)
    assert "invalid" in fake.requests[1]["messages"][-1]["content"]


def test_missing_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASI_ONE_API_KEY", raising=False)
    monkeypatch.delenv("ASI1_API_KEY", raising=False)
    with pytest.raises(ASI1Error, match="asi1.ai"):
        ASI1()


def test_history_keeps_last_turns(ctx) -> None:
    for i in range(5):
        remember(ctx, "s1", "user", f"m{i}", keep=3)
    assert [t["content"] for t in history(ctx, "s1")] == ["m2", "m3", "m4"]
    assert history(ctx, "other") == []
