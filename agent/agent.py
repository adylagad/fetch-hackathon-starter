"""Hackkit Guide: a tour of everything a Fetch.ai hackathon agent can do.

Run it:   uv run python agent.py        (from this folder, with .env filled in)
Then chat with it on ASI:One (https://asi1.ai) by its @handle, or from Agentverse.

Each feature lives in its own file under flows/. Delete the ones you don't need
and keep the pattern: register handlers, return text or cards.
"""

from __future__ import annotations

import os
import re

from fetch_hackkit import HackAgent
from flows import ask, gallery, mcp_demo, menu, paid_brief, peer_demo

agent = HackAgent(
    name="Hackkit Guide",
    handle=os.getenv("AGENT_HANDLE") or None,
    description=(
        "Interactive tour of Fetch.ai agent building: ASI:One interactive cards, "
        "LLM tool calling, FET payments, MCP tools and agent-to-agent messaging."
    ),
    readme_path="README.md",
)

GREETING = re.compile(r"^\s*(hi|hello|hey|yo|menu|start|help|back|home)\b[!. ]*$", re.I)

for flow in (menu, gallery, ask, paid_brief, mcp_demo, peer_demo):
    flow.register(agent)


@agent.on_text
async def on_text(ctx, msg):
    """Greetings open the menu; anything else is a question for the ASI:One-powered guide."""
    if not msg.text or GREETING.match(msg.text):
        return menu.menu_card()
    return await ask.answer(ctx, msg)


if __name__ == "__main__":
    agent.run()
