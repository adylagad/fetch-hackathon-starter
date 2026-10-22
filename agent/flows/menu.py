"""The home menu: a carousel card. Every item's button sends ``{"action": ...}``."""

from __future__ import annotations

from fetch_hackkit import HackAgent, cards


def menu_card() -> cards.Card:
    return cards.carousel(
        "Hackkit Guide",
        [
            cards.item(
                "gallery",
                "Interactive cards",
                action="gallery",
                cta_label="Open gallery",
                subtitle="Carousel, detail, form, review and custom cards, live",
                badges=[cards.badge("ASI:One UI")],
            ),
            cards.item(
                "ask",
                "Ask with tools",
                action="ask_intro",
                cta_label="Try it",
                subtitle="ASI:One LLM calling real tools (Agentverse search)",
                badges=[cards.badge("Tool calling", "success")],
            ),
            cards.item(
                "brief",
                "Paid project brief",
                action="brief_form",
                cta_label="Get a brief",
                subtitle="Payment Protocol: 0.1 testnet FET, verified on-chain",
                badges=[cards.badge("Payments", "warning")],
            ),
            cards.item(
                "mcp",
                "MCP tools",
                action="mcp_form",
                cta_label="Ask a repo",
                subtitle="Ask about any GitHub repo via the DeepWiki MCP server",
                badges=[cards.badge("MCP")],
            ),
            cards.item(
                "peer",
                "Agent-to-agent",
                action="peer_form",
                cta_label="Delegate",
                subtitle="Forward a question to another agent and relay its answer",
                badges=[cards.badge("Multi-agent", "success")],
            ),
        ],
        subtitle="Pick a feature to see how it works",
        narration=(
            "👋 I'm the **Hackkit Guide**. I show what a Fetch.ai agent can do inside ASI:One. "
            "Pick a card, or just ask me anything about building agents."
        ),
    )


def register(agent: HackAgent) -> None:
    @agent.on_action("menu")
    async def show_menu(ctx, msg, sel):
        return menu_card()
