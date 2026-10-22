from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fetch_hackkit import doctor, register
from fetch_hackkit import mcp as hk_mcp
from mcp import Client
from mcp.server.mcpserver import MCPServer


@pytest.mark.parametrize("handle", ["my-agent", "@my_agent", "A.b-1"])
def test_valid_handles(handle: str) -> None:
    assert register.validate_handle(handle) == handle.removeprefix("@")


@pytest.mark.parametrize("handle", ["", "has space", "-lead", "x" * 41, "emoji🙂"])
def test_invalid_handles(handle: str) -> None:
    with pytest.raises(ValueError):
        register.validate_handle(handle)


def _fake_get(status: int, body: dict | None = None):
    def get(url: str, **_kw) -> httpx.Response:
        return httpx.Response(status, json=body or {}, request=httpx.Request("GET", url))

    return get


def test_resolve_and_handle_available(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", _fake_get(404))
    assert register.resolve("@free") is None
    assert register.handle_available("free")
    monkeypatch.setattr(httpx, "get", _fake_get(200, {"address": "agent1qme"}))
    assert not register.handle_available("taken")
    assert register.handle_available("taken", mine="agent1qme")
    assert register.resolve_address("@taken") == "agent1qme"
    assert register.resolve_address("agent1qdirect") == "agent1qdirect"


def test_identity_from_seed_is_deterministic() -> None:
    a = doctor.identity_from_seed("same seed phrase for both calls here")
    assert a == doctor.identity_from_seed("same seed phrase for both calls here")
    assert a[0].startswith("agent1") and a[1].startswith("fetch1")


def test_readme_check(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Agent\n" + "\n".join(doctor.BADGES) + "\nagent1qme\n")
    assert doctor.check_readme(readme, "agent1qme").status == "ok"
    readme.write_text("# Agent\n")
    check = doctor.check_readme(readme, "agent1qme")
    assert check.status == "fail" and "innovationlab" in check.detail and "address" in check.detail
    assert doctor.check_readme(tmp_path / "missing.md", None).status == "fail"


def test_almanac_check(monkeypatch) -> None:
    record = {
        "status": "active",
        "protocols": [doctor.CHAT_PROTOCOL_DIGEST],
        "expiry": "2999-01-01T00:00:00Z",
        "type": "mailbox",
    }
    monkeypatch.setattr(doctor, "resolve", lambda _a: record)
    assert doctor.check_almanac("agent1qme").status == "ok"
    monkeypatch.setattr(doctor, "resolve", lambda _a: {**record, "protocols": []})
    assert "chat protocol" in doctor.check_almanac("agent1qme").detail
    monkeypatch.setattr(doctor, "resolve", lambda _a: None)
    assert doctor.check_almanac("agent1qme").status == "fail"


def test_handle_check(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "resolve", lambda _h: {"address": "agent1qother"})
    assert doctor.check_handle("x", "agent1qme").status == "fail"
    monkeypatch.setattr(doctor, "resolve", lambda _h: {"address": "agent1qme"})
    assert doctor.check_handle("x", "agent1qme").status == "ok"


@pytest.fixture
def mcp_server(monkeypatch) -> MCPServer:
    server = MCPServer("test")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def secret() -> str:
        """Not exposed."""
        return "s"

    monkeypatch.setattr(hk_mcp, "_client", lambda _url, _headers: Client(server))
    return server


async def test_mcp_tools_are_usable_by_run_tools(mcp_server) -> None:
    tools = await hk_mcp.mcp_tools("http://unused", include={"add"}, prefix="calc_")
    assert [t.name for t in tools] == ["calc_add"]
    assert tools[0].parameters["required"] == ["a", "b"]
    assert await tools[0].call({"a": 2, "b": 3}) == {"result": 5}


async def test_connect_mailbox_resends_until_handle_applies(monkeypatch) -> None:
    from fetch_hackkit import HackAgent

    agent = HackAgent("h", handle="my-handle", mailbox=True, auto_connect=False, port=8995)
    state = {"posts": 0, "handle": None}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/challenge"):
            return httpx.Response(200, json={"challenge": "abc"})
        if path == "/v2/identity":
            return httpx.Response(200, json={})
        if path == "/v2/agents" and request.method == "POST":
            state["posts"] += 1
            if state["posts"] > 1:  # Agentverse applies the handle on update only
                state["handle"] = "my-handle"
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"address": agent.address, "handle": state["handle"]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setenv("AGENTVERSE_API_KEY", "test-key")
    result = await register.connect_mailbox(agent)
    assert result.ok and result.detail == ""
    assert state == {"posts": 2, "handle": "my-handle"}
