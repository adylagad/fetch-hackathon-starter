"""Smoke tests: every card the showcase can send is valid, and every button has a handler."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fetch_hackkit.cards import collect_actions, validate  # noqa: E402
from flows import gallery, mcp_demo, menu, paid_brief, peer_demo  # noqa: E402

ALL_CARDS = [
    menu.menu_card(),
    gallery.gallery_card(),
    *(gallery.example(k) for k in gallery.KINDS),
    paid_brief.brief_form(),
    mcp_demo.mcp_form(),
    peer_demo.peer_form(),
]


@pytest.mark.parametrize("card", ALL_CARDS, ids=lambda c: f"{c.kind}:{c.payload.get('title', '')}")
def test_cards_are_valid(card) -> None:
    assert validate(card.kind, card.payload) == []


async def test_every_button_has_a_handler(monkeypatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    import agent as showcase

    actions = set().union(*(collect_actions(c.payload) for c in ALL_CARDS))
    assert actions <= set(showcase.agent._action_handlers), actions - set(
        showcase.agent._action_handlers
    )
