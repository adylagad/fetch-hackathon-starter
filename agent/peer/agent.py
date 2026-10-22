"""Idea Critic: a tiny specialist agent, the second half of a multi-agent system.

Run it in a second terminal:   uv run python peer/agent.py
Copy the address it prints into PEER_AGENT in .env, restart the guide, and the
"Agent-to-agent" demo will delegate to this agent instead of the Weather Agent.
"""

from __future__ import annotations

import os

from fetch_hackkit import ASI1, ASI1Error, HackAgent

critic = HackAgent(
    name="Idea Critic",
    seed=os.getenv("PEER_SEED_PHRASE"),
    port=int(os.getenv("PEER_PORT", "8001")),
    description="Gives blunt, constructive feedback on hackathon project ideas.",
)


@critic.on_text
async def critique(ctx, msg):
    try:
        return await ASI1().ask(
            msg.text,
            system="You are a hackathon judge. In 3 bullets: biggest risk, what's novel, "
            "one feature that would impress judges. Max 80 words.",
        )
    except ASI1Error:
        return f"(no ASI_ONE_API_KEY) Idea received: {msg.text!r}. Ship a demo first!"


if __name__ == "__main__":
    critic.run()
