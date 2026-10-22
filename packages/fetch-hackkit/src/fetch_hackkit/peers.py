"""Talk to other agents over the chat protocol (multi-agent patterns).

    answer = await ask_agent(ctx, "@weather-agent", "Forecast for Berkeley tomorrow?")

Works with any chat-protocol agent on Agentverse, including ones you did not write.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from uagents import Context
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage

from .agent import text_message
from .register import resolve_address


class PeerError(RuntimeError):
    pass


async def ask_agent(ctx: Context, agent: str, text: str, *, timeout: int = 60) -> str:
    """Send ``text`` to ``agent`` (address or ``@handle``) and wait for its text reply.

    The peer's ``ChatAcknowledgement`` is skipped; its next ``ChatMessage`` in this
    session is the answer. Raises :class:`PeerError` on delivery failure or timeout.
    """
    address = await asyncio.to_thread(resolve_address, agent)
    reply, status = await ctx.send_and_receive(
        address, text_message(text), response_type=ChatMessage, timeout=timeout
    )
    if not isinstance(reply, ChatMessage):
        raise PeerError(f"{agent} did not answer: {getattr(status, 'detail', status)}")
    await ctx.send(
        address,
        ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=reply.msg_id),
    )
    return reply.text()
