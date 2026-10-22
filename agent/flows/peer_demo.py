"""Agent-to-agent: forward a question to another chat-protocol agent and relay the answer.

By default it asks Fetch.ai's public Weather Agent. Point ``PEER_AGENT`` at your own
specialist (see ../peer/agent.py) to build a multi-agent system.
"""

from __future__ import annotations

import os

from fetch_hackkit import HackAgent, cards
from fetch_hackkit.peers import PeerError, ask_agent

DEFAULT_PEER = "agent1qfvydlgcxrvga2kqjxhj3hpngegtysm2c7uk48ywdue0kgvtc2f5cwhyffv"  # Weather Agent


def peer() -> str:
    return os.getenv("PEER_AGENT") or DEFAULT_PEER


def peer_form() -> cards.Card:
    return cards.form(
        "Ask another agent",
        [
            cards.field(
                "question",
                "Question",
                required=True,
                placeholder="What's the weather in Berkeley today?",
            )
        ],
        submit=cards.cta("Send to agent", "peer_ask", primary=True),
        narration=f"I'll forward your question to `{peer()[:20]}…` over the chat protocol and relay its answer.",
    )


def register(agent: HackAgent) -> None:
    @agent.on_action("peer_form")
    async def show_form(ctx, msg, sel):
        return peer_form()

    @agent.on_action("peer_ask")
    async def ask(ctx, msg, sel):
        question = str(sel.get("question") or msg.text)
        try:
            answer = await ask_agent(ctx, peer(), question, timeout=60)
        except PeerError as exc:
            return f"The other agent didn't answer in time ({exc}). Try again in a moment."
        return f"🤝 Answer from `{peer()[:20]}…`:\n\n{answer}"
