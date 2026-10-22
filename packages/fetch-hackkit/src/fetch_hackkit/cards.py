"""ASI:One Interactive Cards: builders, validation, and selection parsing.

A card is a normal chat-protocol ``ChatMessage`` with two content blocks:
a ``TextContent`` narration (shown in the chat bubble) and a ``MetadataContent``
declaring the card. When the user taps a button, ASI:One sends the button's
``selection`` back to your agent as text (JSON on a direct @mention, a prose
sentence when routed by the ASI:One planner). :func:`parse_selection` handles both.

Every builder here puts an ``action`` key in each selection, so
``HackAgent.on_action("name")`` can route taps without any parsing code.

Spec: https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

CardKind = Literal["carousel", "detail", "form", "review", "custom"]
CARD_KINDS: tuple[str, ...] = ("carousel", "detail", "form", "review", "custom")
FieldKind = Literal["text", "number", "email", "select", "checkbox"]
BadgeVariant = Literal["info", "success", "warning"]

CARD_PROTOCOL_VERSION = "1"
# ASI:One rejects payloads over 64 KB; stay under it with headroom.
MAX_PAYLOAD_BYTES = 60_000
# Custom card trees may nest at most 8 levels (root = level 1).
MAX_CUSTOM_DEPTH = 8

Selection = dict[str, Any]
Options = list[dict[str, str]] | list[tuple[str, str]] | list[str]
Rows = dict[str, str] | list[tuple[str, str]] | list[dict[str, str]]


class CardError(ValueError):
    """Raised when a card payload would be rejected by ASI:One."""


@dataclass(frozen=True)
class Card:
    """A card ready to send. Return it from a handler, or call :meth:`to_message`."""

    kind: CardKind
    payload: dict[str, Any]
    narration: str = ""
    terminal: bool = False
    drawer_width: int | None = None

    def to_message(self, *, card_id: str | None = None) -> ChatMessage:
        return card_message(
            self.narration,
            self.kind,
            self.payload,
            terminal=self.terminal,
            drawer_width=self.drawer_width,
            card_id=card_id,
        )


# --------------------------------------------------------------------------- #
# Small building blocks shared by the card kinds
# --------------------------------------------------------------------------- #


def selection(action: str, **data: Any) -> Selection:
    """What a button sends back when tapped: ``{"action": action, **data}``."""
    return {"action": action, **data}


def cta(label: str, action: str, *, primary: bool = False, **data: Any) -> dict[str, Any]:
    """A call-to-action button. ``data`` is echoed back with the tap."""
    out: dict[str, Any] = {"label": label, "selection": selection(action, **data)}
    if primary:
        out["primary"] = True
    return out


def badge(label: str, variant: BadgeVariant = "info") -> dict[str, str]:
    return {"label": label, "variant": variant}


def _options(options: Options) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for opt in options:
        if isinstance(opt, dict):
            out.append({"value": str(opt["value"]), "label": str(opt.get("label", opt["value"]))})
        elif isinstance(opt, tuple):
            out.append({"value": str(opt[0]), "label": str(opt[1])})
        else:
            out.append({"value": str(opt), "label": str(opt)})
    return out


def _rows(rows: Rows) -> list[dict[str, str]]:
    if isinstance(rows, dict):
        return [{"label": str(k), "value": str(v)} for k, v in rows.items()]
    out: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append({"label": str(row["label"]), "value": str(row["value"])})
        else:
            out.append({"label": str(row[0]), "value": str(row[1])})
    return out


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
# Card kinds
# --------------------------------------------------------------------------- #


def item(
    id: str,
    title: str,
    *,
    action: str,
    cta_label: str = "Select",
    subtitle: str | None = None,
    image: str | None = None,
    badges: list[dict[str, str]] | None = None,
    secondary_text: str | None = None,
    **data: Any,
) -> dict[str, Any]:
    """One carousel item. The tap sends ``{"action": action, "id": id, **data}``."""
    return _drop_none(
        {
            "id": id,
            "title": title,
            "subtitle": subtitle,
            "image": image,
            "badges": badges,
            "secondary_text": secondary_text,
            "primary_cta": cta(cta_label, action, id=id, **data),
        }
    )


def carousel(
    title: str,
    items: list[dict[str, Any]],
    *,
    subtitle: str | None = None,
    narration: str = "",
    drawer_width: int | None = None,
) -> Card:
    """A horizontally scrollable list; each item has one primary button."""
    payload = _drop_none({"title": title, "subtitle": subtitle, "items": items})
    return Card("carousel", payload, narration, drawer_width=drawer_width)


def radio(name: str, label: str, choices: Options) -> dict[str, Any]:
    """Radio sub-options for a detail card. The chosen value is sent as ``name``."""
    return {"name": name, "kind": "radio", "label": label, "choices": _options(choices)}


def detail(
    title: str,
    *,
    rows: Rows,
    ctas: list[dict[str, Any]],
    hero_image: str | None = None,
    sub_options: dict[str, Any] | None = None,
    narration: str = "",
    drawer_width: int | None = None,
) -> Card:
    """A hero image, key/value rows, optional radio choice, and one or more buttons."""
    payload = _drop_none(
        {
            "title": title,
            "hero_image": hero_image,
            "summary_rows": _rows(rows),
            "sub_options": sub_options,
            "ctas": ctas,
        }
    )
    return Card("detail", payload, narration, drawer_width=drawer_width)


def field(
    name: str,
    label: str,
    kind: FieldKind = "text",
    *,
    required: bool = False,
    options: Options | None = None,
    placeholder: str | None = None,
) -> dict[str, Any]:
    """A form field. ``select`` fields need ``options``."""
    out: dict[str, Any] = {"name": name, "kind": kind, "label": label}
    if required:
        out["required"] = True
    if options is not None:
        out["options"] = _options(options)
    if placeholder is not None:
        out["placeholder"] = placeholder
    return out


def form(
    title: str,
    fields: list[dict[str, Any]],
    *,
    submit: dict[str, Any],
    narration: str = "",
    drawer_width: int | None = None,
) -> Card:
    """Labeled inputs plus a submit button. All field values come back with the tap."""
    payload = {"title": title, "fields": fields, "submit_cta": submit}
    return Card("form", payload, narration, drawer_width=drawer_width)


def review(
    title: str,
    *,
    rows: Rows,
    approve: dict[str, Any],
    reject: dict[str, Any],
    narration: str = "",
    drawer_width: int | None = None,
) -> Card:
    """Summary rows plus approve/reject. Use before anything irreversible (payments, bookings)."""
    payload = {
        "title": title,
        "summary_rows": _rows(rows),
        "approve_cta": approve,
        "reject_cta": reject,
    }
    return Card("review", payload, narration, drawer_width=drawer_width)


def custom(root: dict[str, Any], *, narration: str = "", drawer_width: int | None = None) -> Card:
    """A free-form layout built from :class:`ui` primitives."""
    return Card("custom", {"root": root}, narration, drawer_width=drawer_width)


def info(title: str, *, rows: Rows, narration: str = "") -> Card:
    """A terminal (read-only) detail card that expects no input."""
    payload = {"title": title, "summary_rows": _rows(rows), "ctas": []}
    return Card("detail", payload, narration, terminal=True)


class ui:
    """Primitives for :func:`custom` cards, e.g. ``ui.section("Hi", [ui.text("...")])``."""

    @staticmethod
    def section(
        title: str | None, children: list[dict[str, Any]], *, subtitle: str | None = None
    ) -> dict[str, Any]:
        return _drop_none(
            {"type": "section", "title": title, "subtitle": subtitle, "children": children}
        )

    @staticmethod
    def group(
        children: list[dict[str, Any]],
        *,
        direction: Literal["row", "column"] = "row",
        gap: int | None = None,
    ) -> dict[str, Any]:
        return _drop_none(
            {"type": "group", "direction": direction, "gap": gap, "children": children}
        )

    @staticmethod
    def divider() -> dict[str, Any]:
        return {"type": "divider"}

    @staticmethod
    def text(
        value: str, style: Literal["body", "muted", "emphasis"] | None = None
    ) -> dict[str, Any]:
        return _drop_none({"type": "text", "value": value, "style": style})

    @staticmethod
    def heading(value: str, level: Literal[1, 2, 3] | None = None) -> dict[str, Any]:
        return _drop_none({"type": "heading", "value": value, "level": level})

    @staticmethod
    def image(src: str, alt: str | None = None, aspect_ratio: str | None = None) -> dict[str, Any]:
        return _drop_none({"type": "image", "src": src, "alt": alt, "aspect_ratio": aspect_ratio})

    @staticmethod
    def badge(label: str, variant: BadgeVariant | None = None) -> dict[str, Any]:
        return _drop_none({"type": "badge", "label": label, "variant": variant})

    @staticmethod
    def button(label: str, action: str, *, primary: bool = False, **data: Any) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": "button",
            "label": label,
            "action": {"selection": selection(action, **data)},
        }
        if primary:
            out["primary"] = True
        return out

    @staticmethod
    def input(
        name: str,
        label: str,
        kind: FieldKind = "text",
        *,
        required: bool = False,
        options: Options | None = None,
        placeholder: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "input",
            **field(name, label, kind, required=required, options=options, placeholder=placeholder),
        }

    @staticmethod
    def list_items(items: list[dict[str, Any]]) -> dict[str, Any]:
        """``items``: dicts from :meth:`list_item`."""
        return {"type": "list", "items": items}

    @staticmethod
    def list_item(
        children: list[dict[str, Any]], action: str | None = None, **data: Any
    ) -> dict[str, Any]:
        out: dict[str, Any] = {"children": children}
        if action:
            out["action"] = {"selection": selection(action, **data)}
        return out

    @staticmethod
    def choice_grid(
        name: str, choices: list[dict[str, str]], *, multi: bool = False
    ) -> dict[str, Any]:
        """``choices``: ``[{"value": ..., "label": ..., "image": optional}]``."""
        out: dict[str, Any] = {"type": "choice_grid", "name": name, "choices": choices}
        if multi:
            out["multi"] = True
        return out


# --------------------------------------------------------------------------- #
# Validation + message assembly
# --------------------------------------------------------------------------- #


def _depth(node: Any) -> int:
    if isinstance(node, dict):
        kids = node.get("children") or []
        items = node.get("items") if node.get("type") == "list" else None
        nested = list(kids) + [c for it in (items or []) for c in it.get("children", [])]
        return 1 + max((_depth(c) for c in nested), default=0)
    return 0


def _ctas_ok(ctas: Any) -> bool:
    return isinstance(ctas, dict) and isinstance(ctas.get("selection"), dict) and "label" in ctas


def validate(kind: str, payload: dict[str, Any]) -> list[str]:
    """Return the problems ASI:One would reject this card for (empty list = valid)."""
    errors: list[str] = []
    if kind not in CARD_KINDS:
        return [f"unknown card kind {kind!r}; use one of {', '.join(CARD_KINDS)}"]
    try:
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        return [f"payload is not JSON-serialisable: {exc}"]
    if size > MAX_PAYLOAD_BYTES:
        errors.append(f"payload is {size} bytes; keep it under {MAX_PAYLOAD_BYTES}")

    if kind == "carousel":
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            errors.append("carousel needs a non-empty 'items' list")
        else:
            for i, it in enumerate(items):
                if not it.get("title"):
                    errors.append(f"items[{i}] needs a 'title'")
                if not _ctas_ok(it.get("primary_cta")):
                    errors.append(f"items[{i}] needs a 'primary_cta' with label + selection")
    elif kind == "detail":
        if not isinstance(payload.get("ctas"), list):
            errors.append("detail needs a 'ctas' list")
        for i, c in enumerate(payload.get("ctas") or []):
            if not _ctas_ok(c):
                errors.append(f"ctas[{i}] needs label + selection")
    elif kind == "form":
        fields = payload.get("fields")
        if not isinstance(fields, list) or not fields:
            errors.append("form needs a non-empty 'fields' list")
        for f in fields or []:
            if f.get("kind") == "select" and not f.get("options"):
                errors.append(f"select field {f.get('name')!r} needs non-empty 'options'")
        if not _ctas_ok(payload.get("submit_cta")):
            errors.append("form needs a 'submit_cta' with label + selection")
    elif kind == "review":
        for key in ("approve_cta", "reject_cta"):
            if not _ctas_ok(payload.get(key)):
                errors.append(f"review needs '{key}' with label + selection")
    elif kind == "custom":
        root = payload.get("root")
        if not isinstance(root, dict) or "type" not in root:
            errors.append("custom card needs a 'root' node with a 'type'")
        elif (d := _depth(root)) > MAX_CUSTOM_DEPTH:
            errors.append(f"custom tree is {d} levels deep; max is {MAX_CUSTOM_DEPTH}")
    return errors


def _stamp_card_id(node: Any, card_id: str) -> None:
    if isinstance(node, dict):
        sel = node.get("selection")
        if isinstance(sel, dict):
            sel["card_id"] = card_id
        for value in node.values():
            _stamp_card_id(value, card_id)
    elif isinstance(node, list):
        for value in node:
            _stamp_card_id(value, card_id)


def card_message(
    narration: str,
    kind: str,
    payload: dict[str, Any],
    *,
    terminal: bool = False,
    drawer_width: int | None = None,
    card_id: str | None = None,
) -> ChatMessage:
    """Build the ``ChatMessage`` for a card. Raises :class:`CardError` if invalid.

    ``card_id`` is stamped into every selection so you can ignore taps on an
    older card (``parse_selection(...)["card_id"]``).
    """
    errors = validate(kind, payload)
    if errors:
        raise CardError(f"invalid {kind} card: " + "; ".join(errors))
    if card_id:
        payload = copy.deepcopy(payload)
        _stamp_card_id(payload, card_id)
    metadata = {
        "card_protocol_version": CARD_PROTOCOL_VERSION,
        "requires_card_interaction": "true",
        "card_kind": kind,
        "card_payload": json.dumps(payload, ensure_ascii=False),
    }
    if terminal:
        metadata["is_terminal"] = "true"
    if drawer_width:
        metadata["preferred_drawer_width_px"] = str(max(320, min(800, int(drawer_width))))
    if card_id:
        metadata["card_id"] = card_id
    content: list[Any] = []
    if narration:
        content.append(TextContent(type="text", text=narration))
    content.append(MetadataContent(type="metadata", metadata=metadata))
    return ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(), content=content)


# --------------------------------------------------------------------------- #
# Reading taps back
# --------------------------------------------------------------------------- #

_MENTION_PREFIX = re.compile(r"^(?:@\S+\s+)+")


def strip_mention(text: str) -> str:
    """Remove leading ``@handle`` mentions (``"@my-agent hi"`` -> ``"hi"``)."""
    return _MENTION_PREFIX.sub("", (text or "").strip()).strip()


def collect_actions(payload: dict[str, Any]) -> set[str]:
    """Every ``action`` a card can send back. Useful as ``known_actions``."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            sel = node.get("selection")
            if isinstance(sel, dict) and sel.get("action"):
                found.add(str(sel["action"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def parse_selection(text: str, known_actions: set[str] | None = None) -> Selection:
    """Recover a card tap from an inbound message; ``{}`` if it is ordinary text.

    1. Direct @mention: the selection arrives as JSON -> returned as a dict
       (a nested ``"selection"`` object is flattened to the top level).
    2. Planner-routed: the selection arrives as prose that contains every
       identifier from the selection -> we look for a known action token and
       return ``{"action": ..., "prose": text}``.
    """
    raw = (text or "").strip()
    if not raw:
        return {}
    for candidate in (strip_mention(raw), raw):
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            nested = data.get("selection")
            if not data.get("action") and isinstance(nested, dict):
                data = {**{k: v for k, v in data.items() if k != "selection"}, **nested}
            return data
    if known_actions:
        lowered = raw.lower()
        # Longest first so "book_confirm" wins over "book".
        for action in sorted(known_actions, key=len, reverse=True):
            if action and re.search(rf"(?<![\w-]){re.escape(action.lower())}(?![\w-])", lowered):
                return {"action": action, "prose": raw}
    return {}
