from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fetch_hackkit import HackAgent, cards
from fetch_hackkit.agent import to_messages
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    StartSessionContent,
    TextContent,
)

USER = "agent1quser"


def _msg(*content) -> ChatMessage:
    return ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(), content=list(content))


def _text(t: str) -> ChatMessage:
    return _msg(TextContent(type="text", text=t))


def _texts(ctx) -> list[str]:
    return [m.text() for _, m in ctx.sent if isinstance(m, ChatMessage)]


@pytest.fixture
async def agent() -> HackAgent:  # async: uagents grabs the running loop at init
    return HackAgent("test", mailbox=False, port=8999)


async def test_requires_seed(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_SEED_PHRASE")
    monkeypatch.setattr("fetch_hackkit.agent.load_dotenv", lambda *_: None)
    with pytest.raises(ValueError, match="AGENT_SEED_PHRASE"):
        HackAgent("x", mailbox=False)


async def test_rejects_bad_handle() -> None:
    with pytest.raises(ValueError):
        HackAgent("x", mailbox=False, handle="has spaces")


def test_chat_protocol_included(agent: HackAgent) -> None:
    assert agent.chat_protocol.digest in agent.protocols


async def test_text_is_acked_stripped_and_answered(agent: HackAgent, ctx) -> None:
    seen = {}

    @agent.on_text
    async def on_text(ctx, msg):
        seen["text"] = msg.text
        return f"echo: {msg.text}"

    incoming = _text("@test hello there")
    await agent._on_chat_message(ctx, USER, incoming)
    assert isinstance(ctx.sent[0][1], ChatAcknowledgement)
    assert ctx.sent[0][1].acknowledged_msg_id == incoming.msg_id
    assert seen["text"] == "hello there"
    assert _texts(ctx) == ["echo: hello there"]


async def test_start_session_only_is_just_acked(agent: HackAgent, ctx) -> None:
    await agent._on_chat_message(ctx, USER, _msg(StartSessionContent(type="start-session")))
    assert len(ctx.sent) == 1 and isinstance(ctx.sent[0][1], ChatAcknowledgement)


async def test_card_tap_routes_to_action(agent: HackAgent, ctx) -> None:
    @agent.on_action("pick")
    async def pick(ctx, msg, sel):
        return [f"picked {sel['id']}", cards.info("Done", rows={"id": sel["id"]})]

    await agent._on_chat_message(ctx, USER, _text('{"action": "pick", "id": "t1"}'))
    replies = [m for _, m in ctx.sent if isinstance(m, ChatMessage)]
    assert replies[0].text() == "picked t1"
    assert any(isinstance(c, MetadataContent) for c in replies[1].content)


async def test_prose_tap_uses_actions_from_sent_cards(agent: HackAgent, ctx) -> None:
    @agent.on_text
    async def on_text(ctx, msg):
        if msg.action:
            return f"action={msg.action}"
        return cards.carousel("Menu", [cards.item("a", "A", action="open_gallery")])

    await agent._on_chat_message(ctx, USER, _text("hi"))
    await agent._on_chat_message(ctx, USER, _text("The user chose open_gallery from the menu"))
    assert _texts(ctx)[-1] == "action=open_gallery"


async def test_handler_errors_become_friendly_reply(agent: HackAgent, ctx) -> None:
    @agent.on_text
    async def boom(ctx, msg):
        raise RuntimeError("kaboom")

    await agent._on_chat_message(ctx, USER, _text("hi"))
    assert _texts(ctx) == [agent.error_message]


async def test_no_handler_default(agent: HackAgent, ctx) -> None:
    await agent._on_chat_message(ctx, USER, _text("hi"))
    assert "on_text" in _texts(ctx)[0]


def test_to_messages_normalises() -> None:
    assert to_messages(None) == []
    assert to_messages("   ") == []
    assert len(to_messages(["a", cards.info("t", rows={"a": "b"})])) == 2
    with pytest.raises(TypeError):
        to_messages([42])  # type: ignore[list-item]
