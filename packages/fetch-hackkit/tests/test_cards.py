from __future__ import annotations

import json

import pytest
from fetch_hackkit import cards
from fetch_hackkit.cards import CardError, card_message, parse_selection, ui, validate
from uagents_core.contrib.protocols.chat import MetadataContent, TextContent


def _meta(msg) -> dict[str, str]:
    return next(c for c in msg.content if isinstance(c, MetadataContent)).metadata


def test_carousel_matches_documented_shape() -> None:
    card = cards.carousel(
        "Pick a train",
        [cards.item("t1", "Express", action="pick", subtitle="2h", badges=[cards.badge("Fast")])],
        narration="Here you go",
    )
    item = card.payload["items"][0]
    assert item["primary_cta"] == {"label": "Select", "selection": {"action": "pick", "id": "t1"}}
    assert item["badges"] == [{"label": "Fast", "variant": "info"}]
    assert "image" not in item  # None fields are dropped
    msg = card.to_message()
    assert isinstance(msg.content[0], TextContent) and msg.content[0].text == "Here you go"
    meta = _meta(msg)
    assert meta["card_kind"] == "carousel"
    assert meta["card_protocol_version"] == "1"
    assert meta["requires_card_interaction"] == "true"
    assert json.loads(meta["card_payload"])["title"] == "Pick a train"


def test_detail_form_review_shapes() -> None:
    d = cards.detail(
        "Trip",
        rows={"Departs": "09:00"},
        sub_options=cards.radio("seat", "Seat", [("2nd", "Second")]),
        ctas=[cards.cta("Go", "go", primary=True)],
    )
    assert d.payload["summary_rows"] == [{"label": "Departs", "value": "09:00"}]
    assert d.payload["sub_options"]["choices"] == [{"value": "2nd", "label": "Second"}]
    assert d.payload["ctas"][0] == {"label": "Go", "selection": {"action": "go"}, "primary": True}

    f = cards.form(
        "Details",
        [cards.field("country", "Country", "select", options=["FR", "US"], required=True)],
        submit=cards.cta("Submit", "submit"),
    )
    assert f.payload["fields"][0]["options"] == [
        {"value": "FR", "label": "FR"},
        {"value": "US", "label": "US"},
    ]
    assert f.payload["submit_cta"]["selection"] == {"action": "submit"}

    r = cards.review(
        "Confirm",
        rows=[("Total", "EUR 45")],
        approve=cards.cta("Yes", "ok"),
        reject=cards.cta("No", "no"),
    )
    assert set(r.payload) == {"title", "summary_rows", "approve_cta", "reject_cta"}
    for card in (d, f, r):
        assert validate(card.kind, card.payload) == []


def test_custom_card_primitives() -> None:
    root = ui.section(
        "Hotels",
        [
            ui.choice_grid("hotel", [{"value": "h1", "label": "Riverside"}]),
            ui.group([ui.button("Book", "book", primary=True), ui.button("Back", "menu")]),
        ],
    )
    card = cards.custom(root)
    assert validate("custom", card.payload) == []
    assert cards.collect_actions(card.payload) == {"book", "menu"}


def test_validation_errors() -> None:
    assert validate("nope", {}) == [
        "unknown card kind 'nope'; use one of carousel, detail, form, review, custom"
    ]
    assert any(
        "select field" in e
        for e in validate(
            "form",
            {"fields": [{"name": "x", "kind": "select"}], "submit_cta": cards.cta("s", "s")},
        )
    )
    assert validate("carousel", {"items": []})
    huge = {"items": [cards.item("a", "x" * 70_000, action="a")]}
    assert any("bytes" in e for e in validate("carousel", huge))

    node: dict = ui.text("leaf")
    for _ in range(9):
        node = ui.section(None, [node])
    assert any("levels deep" in e for e in validate("custom", {"root": node}))

    with pytest.raises(CardError):
        card_message("x", "carousel", {"items": []})


def test_terminal_and_card_id_stamping() -> None:
    card = cards.carousel("t", [cards.item("a", "A", action="pick")])
    msg = card_message("", card.kind, card.payload, terminal=True, card_id="c1", drawer_width=2000)
    meta = _meta(msg)
    assert meta["is_terminal"] == "true"
    assert meta["preferred_drawer_width_px"] == "800"
    assert (
        json.loads(meta["card_payload"])["items"][0]["primary_cta"]["selection"]["card_id"] == "c1"
    )
    assert "card_id" not in card.payload["items"][0]["primary_cta"]["selection"]  # not mutated
    assert len(msg.content) == 1  # no empty narration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"action": "pick", "id": "t1"}', {"action": "pick", "id": "t1"}),
        ('@my-agent {"action": "pick"}', {"action": "pick"}),
        (
            '{"selection": {"action": "book", "hotel": "h1"}, "card_id": "c"}',
            {"action": "book", "hotel": "h1", "card_id": "c"},
        ),
        (
            "The user selected pick for trip t1",
            {"action": "pick", "prose": "The user selected pick for trip t1"},
        ),
        ("just chatting", {}),
        ("", {}),
    ],
)
def test_parse_selection(text: str, expected: dict) -> None:
    assert parse_selection(text, {"pick", "book"}) == expected


def test_parse_selection_prefers_longest_action_and_word_boundaries() -> None:
    assert (
        parse_selection("user chose book_confirm", {"book", "book_confirm"})["action"]
        == "book_confirm"
    )
    assert parse_selection("facebook is great", {"book"}) == {}
