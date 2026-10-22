"""Payment Protocol: a form collects the topic, ``@agent.paid`` charges 0.1 testnet FET,
and the brief is generated only after the payment verifies on-chain.
"""

from __future__ import annotations

from fetch_hackkit import ASI1, ASI1Error, HackAgent, cards
from pydantic import BaseModel

PRICE = "0.1"


class Brief(BaseModel):
    title: str
    problem: str
    agents: list[str]
    fetch_features: list[str]
    demo_script: str


def brief_form() -> cards.Card:
    return cards.form(
        "Project brief",
        [
            cards.field(
                "topic",
                "What do you want to build?",
                required=True,
                placeholder="Agents that split rent and chores",
            ),
            cards.field("team", "Team size", "select", options=["1", "2", "3", "4"]),
        ],
        submit=cards.cta(f"Pay {PRICE} FET and generate", "brief", primary=True),
        narration=(
            f"Describe your idea and I'll write a hackathon project brief for **{PRICE} testnet FET**. "
            "This demonstrates the Payment Protocol: you'll get a payment request, and the brief "
            "is generated only after the transfer verifies on-chain."
        ),
    )


async def write_brief(topic: str, team: str) -> cards.Card | str:
    try:
        brief = await ASI1().structured(
            f"Write a Fetch.ai hackathon project brief for: {topic}. Team size: {team}.",
            Brief,
            system="You are a hackathon mentor. Be specific and realistic for a 36-hour build.",
        )
    except ASI1Error:
        return f"✅ Payment verified! (Set ASI_ONE_API_KEY to generate a real brief for '{topic}'.)"
    return cards.detail(
        brief.title,
        rows={
            "Problem": brief.problem,
            "Agents": ", ".join(brief.agents),
            "Fetch.ai features": ", ".join(brief.fetch_features),
        },
        ctas=[cards.cta("Back to menu", "menu")],
        narration=f"✅ Payment verified. Here's your brief.\n\n**Demo script:** {brief.demo_script}",
    )


def register(agent: HackAgent) -> None:
    @agent.on_action("brief_form")
    async def show_form(ctx, msg, sel):
        return brief_form()

    @agent.paid("brief", amount=PRICE, description="Hackathon project brief")
    async def brief(ctx, msg, sel):
        topic = sel.get("topic") or msg.text or "an agent that helps students"
        return await write_brief(str(topic), str(sel.get("team") or "3"))
