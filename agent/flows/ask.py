"""ASI:One with tool calling: the model decides when to search Agentverse or link docs.

Shows: plain Python functions as tools, per-conversation memory, and graceful
fallback when no ASI:One key is configured.
"""

from __future__ import annotations

import httpx
from fetch_hackkit import ASI1, ASI1Error, HackAgent, history, remember

SYSTEM = (
    "You are the Hackkit Guide, helping hackathon builders use Fetch.ai: uAgents, Agentverse, "
    "ASI:One, the chat and payment protocols, interactive cards and MCP. Be concise and "
    "practical. Use tools to find real agents or the right docs page instead of guessing. "
    "Format answers in short Markdown."
)

DOCS = {
    "uagents": "https://uagents.fetch.ai/docs",
    "chat protocol": "https://innovationlab.fetch.ai/resources/docs/examples/chat-protocol/asi-compatible-uagents",
    "interactive cards": "https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards",
    "payment protocol": "https://uagents.fetch.ai/docs/guides/agent-payment-protocol",
    "asi1 api": "https://docs.asi1.ai/documentation/getting-started/overview",
    "agentverse": "https://docs.agentverse.ai",
    "mcp": "https://innovationlab.fetch.ai/resources/docs/mcp-integration/what-is-mcp",
    "mailbox": "https://innovationlab.fetch.ai/resources/docs/agent-creation/uagent-creation",
    "examples": "https://github.com/fetchai/innovation-lab-examples",
}


async def search_agentverse(query: str, limit: int = 5) -> list[dict]:
    """Search Agentverse for live agents that match a need.

    Args:
        query: What the agent should do, e.g. "flight booking" or "weather".
        limit: How many agents to return (1-10).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://agentverse.ai/v1/search/agents",
            json={"search_text": query, "limit": max(1, min(limit, 10))},
        )
        resp.raise_for_status()
    return [
        {
            "name": a.get("name"),
            "address": a.get("address"),
            "handle": a.get("handle"),
            "description": (a.get("description") or "")[:200],
            "rating": a.get("rating"),
            "interactions": a.get("total_interactions"),
        }
        for a in resp.json().get("agents", [])
    ]


def docs_link(topic: str) -> str:
    """Official documentation link for a Fetch.ai topic.

    Args:
        topic: One of: uagents, chat protocol, interactive cards, payment protocol,
            asi1 api, agentverse, mcp, mailbox, examples.
    """
    key = topic.lower().strip()
    for name, url in DOCS.items():
        if name in key or key in name:
            return url
    return "No exact page. Start at https://innovationlab.fetch.ai/resources/docs"


async def answer(ctx, msg) -> str:
    try:
        llm = ASI1()
    except ASI1Error:
        return (
            "I need an `ASI_ONE_API_KEY` to answer free-form questions. "
            "Meanwhile, say **menu** to explore the demos."
        )
    past = history(ctx, msg.session)
    reply = await llm.run_tools(
        [*past, {"role": "user", "content": msg.text}],
        tools=[search_agentverse, docs_link],
        system=SYSTEM,
        on_call=lambda name, args, _r: ctx.logger.info(f"tool {name}({args})"),
    )
    remember(ctx, msg.session, "user", msg.text)
    remember(ctx, msg.session, "assistant", reply)
    return reply


def register(agent: HackAgent) -> None:
    @agent.on_action("ask_intro")
    async def intro(ctx, msg, sel):
        return (
            "Ask me anything, and I'll use **ASI:One tool calling** to look things up. Try:\n"
            "- *Find agents on Agentverse that can book flights*\n"
            "- *Where are the docs for the payment protocol?*\n"
            "- *Which agents give weather forecasts, and how popular are they?*"
        )
