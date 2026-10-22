"""Card gallery: one live example of each card kind, plus a form -> review -> confirm flow.

Every reply also shows the selection your handler received, so you can see
exactly what a tap looks like on the agent side.
"""

from __future__ import annotations

import json
import re

from fetch_hackkit import HackAgent, cards
from fetch_hackkit.cards import ui

KINDS = {
    "carousel": "Scrollable items, one button each. Menus, search results.",
    "detail": "Hero image, key/value rows, a radio choice and buttons. One item in depth.",
    "form": "Text, number, email, select and checkbox fields. Collect input.",
    "review": "Summary + approve/reject. Confirm anything irreversible.",
    "custom": "Free layout from primitives (this gallery is one).",
}


def _received(sel: dict) -> str:
    shown = {k: v for k, v in sel.items() if k != "prose"}
    how = "planner prose" if "prose" in sel else "JSON"
    return f"\n\n_Your agent received ({how}):_ `{json.dumps(shown)}`"


def gallery_card() -> cards.Card:
    rows = [
        ui.list_item(
            [ui.heading(kind, level=3), ui.text(text, "muted")],
            "gallery_show",
            kind=kind,
        )
        for kind, text in KINDS.items()
    ]
    return cards.custom(
        ui.section(
            "Card gallery",
            [ui.list_items(rows), ui.divider(), ui.button("Back to menu", "menu")],
            subtitle="Tap a card kind to see it",
        ),
        narration="Here are the five ASI:One card kinds. Tap one to see it live.",
    )


def example(kind: str) -> cards.Card:
    if kind == "carousel":
        return cards.carousel(
            "Hack ideas",
            [
                cards.item(
                    "1",
                    "Campus food rescue",
                    action="gallery_pick",
                    subtitle="Agents match leftovers to students",
                    badges=[cards.badge("Impact")],
                ),
                cards.item(
                    "2",
                    "Trip negotiator",
                    action="gallery_pick",
                    subtitle="Agents haggle hotels and flights",
                    badges=[cards.badge("Payments", "warning")],
                ),
                cards.item(
                    "3",
                    "Lab scheduler",
                    action="gallery_pick",
                    subtitle="Multi-agent booking across labs",
                    badges=[cards.badge("Multi-agent", "success")],
                ),
            ],
            narration="A **carousel**: each item has one primary button.",
        )
    if kind == "detail":
        return cards.detail(
            "Trip negotiator",
            hero_image="https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=800",
            rows={"Agents": "3", "Protocols": "Chat + Payment", "Difficulty": "Medium"},
            sub_options=cards.radio("track", "Track", [("asi", "ASI:One"), ("pay", "Payments")]),
            ctas=[
                cards.cta("Use this idea", "gallery_pick", primary=True, id="2"),
                cards.cta("Back", "gallery"),
            ],
            narration="A **detail** card: rows, a radio choice, and buttons. The radio value comes back with the tap.",
        )
    if kind in ("form", "review"):
        return signup_form()
    return gallery_card()


def signup_form() -> cards.Card:
    return cards.form(
        "Team signup",
        [
            cards.field("team", "Team name", required=True, placeholder="The Agentics"),
            cards.field("email", "Contact email", "email", required=True),
            cards.field("size", "Team size", "number"),
            cards.field(
                "track", "Track", "select", options=[("asi", "ASI:One Agent"), ("pay", "Payments")]
            ),
            cards.field("first", "First hackathon?", "checkbox"),
        ],
        submit=cards.cta("Continue", "gallery_review"),
        narration="A **form**: all field values come back with the submit tap. Submit to see a **review** card.",
    )


def register(agent: HackAgent) -> None:
    @agent.on_action("gallery")
    async def show_gallery(ctx, msg, sel):
        return gallery_card()

    @agent.on_action("gallery_show")
    async def show_kind(ctx, msg, sel):
        kind = str(sel.get("kind", ""))
        if kind not in KINDS and "prose" in sel:  # planner prose: find the kind word
            kind = next((k for k in KINDS if k in msg.text.lower()), "custom")
        return example(kind)

    @agent.on_action("gallery_pick")
    async def picked(ctx, msg, sel):
        # Prose taps carry every selection value in the sentence; recover the id from it.
        found = re.search(r"\b([1-3])\b", msg.text)
        idea = sel.get("id") or (found.group(1) if found else "?")
        return f"You picked idea **{idea}**.{_received(sel)}"

    @agent.on_action("gallery_review")
    async def review(ctx, msg, sel):
        if "prose" in sel:  # values only arrive as JSON on a direct @mention
            return (
                "Got your form (as a sentence). Try again with @-mentioning me to see the raw JSON."
            )
        rows = {k.title(): str(sel.get(k, "")) for k in ("team", "email", "size", "track", "first")}
        return cards.review(
            "Confirm signup",
            rows=rows,
            approve=cards.cta(
                "Confirm", "gallery_confirm", primary=True, team=str(sel.get("team", ""))
            ),
            reject=cards.cta("Edit", "gallery_show", kind="form"),
            narration=f"A **review** card before an irreversible step.{_received(sel)}",
        )

    @agent.on_action("gallery_confirm")
    async def confirm(ctx, msg, sel):
        return [
            f"✅ Team **{sel.get('team', 'your team')}** is signed up (demo only, nothing saved).",
            cards.info(
                "What just happened",
                rows={
                    "1": "form card collected input",
                    "2": "review card confirmed it",
                    "3": "on_action handlers routed each tap",
                },
            ),
        ]
