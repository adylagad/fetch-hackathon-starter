"""``HackAgent``: a uAgent that already speaks the Agent Chat Protocol.

What you get over a plain ``uagents.Agent``:

* the chat protocol is included and its manifest published (ASI:One needs this);
* every message is acknowledged, session start/end content is handled;
* ``@agent.on_text`` receives clean text (leading ``@handle`` mentions removed);
* ``@agent.on_action("name")`` receives interactive-card taps, already parsed;
* handlers just *return* a reply: ``str``, :class:`~fetch_hackkit.cards.Card`,
  ``ChatMessage``, or a list of those;
* if a handler raises, the user gets a friendly message instead of silence;
* ``@agent.paid(...)`` puts any action behind the Payment Protocol;
* with ``AGENTVERSE_API_KEY`` set, a mailbox agent connects itself to
  Agentverse on startup (no inspector click), with name, ``@handle``,
  description and README.

It *is* a ``uagents.Agent``, so ``on_interval``, ``storage``, ``include`` and
everything else still work.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import warnings
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeAlias
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    MetadataContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from .cards import Card, collect_actions, parse_selection, strip_mention
from .register import validate_handle

if TYPE_CHECKING:
    from .payments import Paywall

DEFAULT_ERROR_MESSAGE = (
    "Sorry, something went wrong on my side while handling that. Please try again in a moment."
)

ReplyPart: TypeAlias = str | Card | ChatMessage
Reply: TypeAlias = ReplyPart | Sequence[ReplyPart] | None
TextHandler: TypeAlias = Callable[[Context, "Inbound"], Awaitable[Reply]]
ActionHandler: TypeAlias = Callable[[Context, "Inbound", dict[str, Any]], Awaitable[Reply]]


@dataclass
class Inbound:
    """One user message, already unpacked."""

    sender: str
    text: str
    """Text with leading ``@handle`` mentions stripped."""
    session: str
    """Conversation id; use it to key per-conversation state in ``ctx.storage``."""
    raw: ChatMessage
    metadata: dict[str, str] = field(default_factory=dict)
    selection: dict[str, Any] = field(default_factory=dict)
    """Parsed card tap (``{}`` for ordinary text)."""

    @property
    def action(self) -> str | None:
        value = self.selection.get("action")
        return str(value) if value else None


def text_message(text: str, *, end_session: bool = False) -> ChatMessage:
    """A plain chat-protocol text message."""
    content: list[Any] = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(), content=content)


def to_messages(reply: Reply) -> list[ChatMessage]:
    """Normalise anything a handler may return into chat messages."""
    if reply is None:
        return []
    parts: Sequence[ReplyPart] = (
        [reply] if isinstance(reply, str | Card | ChatMessage) else reply  # type: ignore[list-item]
    )
    out: list[ChatMessage] = []
    for part in parts:
        if isinstance(part, ChatMessage):
            out.append(part)
        elif isinstance(part, Card):
            out.append(part.to_message())
        elif isinstance(part, str):
            if part.strip():
                out.append(text_message(part))
        else:
            raise TypeError(f"handlers must return str, Card or ChatMessage, got {type(part)!r}")
    return out


def _event_loop() -> asyncio.AbstractEventLoop:
    """The loop uAgents should use. On Python 3.14+ there is no implicit main-thread
    loop, and ``uagents.Agent()`` at module level crashes without this."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class HackAgent(Agent):
    """A chat-protocol-ready ``uagents.Agent``. See the module docstring."""

    def __init__(
        self,
        name: str,
        *,
        seed: str | None = None,
        port: int | None = None,
        mailbox: bool = True,
        handle: str | None = None,
        description: str | None = None,
        readme_path: str | None = None,
        avatar_url: str | None = None,
        error_message: str = DEFAULT_ERROR_MESSAGE,
        auto_connect: bool = True,
        **agent_kwargs: Any,
    ) -> None:
        load_dotenv(find_dotenv(usecwd=True))
        seed = seed or os.getenv("AGENT_SEED_PHRASE")
        if not seed:
            raise ValueError(
                "No seed phrase. Set AGENT_SEED_PHRASE in .env to any long random phrase and keep "
                "it secret: the seed *is* your agent's identity (address + wallet). "
                "Run `hackkit seed` to generate one."
            )
        if handle:
            validate_handle(handle)
        agent_kwargs.setdefault("loop", _event_loop())
        super().__init__(
            name=name,
            seed=seed,
            port=port or int(os.getenv("AGENT_PORT", "8000")),
            mailbox=mailbox,
            handle=handle,
            description=description,
            readme_path=readme_path,
            avatar_url=avatar_url,
            publish_agent_details=True,
            **agent_kwargs,
        )
        self.error_message = error_message
        self._text_handler: TextHandler | None = None
        self._action_handlers: dict[str, ActionHandler] = {}
        self._known_actions: set[str] = set()
        self._paywall: Paywall | None = None

        self.chat_protocol = Protocol(spec=chat_protocol_spec)
        self.chat_protocol.on_message(ChatMessage)(self._on_chat_message)
        self.chat_protocol.on_message(ChatAcknowledgement)(self._on_chat_ack)
        self.include(self.chat_protocol, publish_manifest=True)

        if mailbox and auto_connect:
            self.on_event("startup")(self._auto_connect)

    # ------------------------------------------------------------------ #
    # Decorators
    # ------------------------------------------------------------------ #

    def on_text(self, func: TextHandler) -> TextHandler:
        """Handle ordinary text (and card taps with no matching ``on_action``)."""
        self._text_handler = func
        return func

    def on_action(self, name: str) -> Callable[[ActionHandler], ActionHandler]:
        """Handle card taps whose selection has ``{"action": name}``."""

        def decorator(func: ActionHandler) -> ActionHandler:
            self._action_handlers[name] = func
            self._known_actions.add(name)
            return func

        return decorator

    def paid(
        self,
        name: str,
        *,
        amount: str,
        currency: str = "FET",
        description: str | None = None,
    ) -> Callable[[ActionHandler], ActionHandler]:
        """Put action ``name`` behind a payment. The handler runs only after payment.

        Tapping a button with ``action=name`` (or calling :meth:`charge`) sends the
        user a ``RequestPayment``; when the user's ``CommitPayment`` verifies
        on-chain, the handler runs with the original message and selection.
        """
        from .payments import Paywall, Product

        if self._paywall is None:
            self._paywall = Paywall(self)
        paywall = self._paywall

        def decorator(func: ActionHandler) -> ActionHandler:
            paywall.add(
                Product(
                    name=name,
                    amount=amount,
                    currency=currency,
                    description=description or name,
                    handler=func,
                )
            )

            async def request(ctx: Context, msg: Inbound, sel: dict[str, Any]) -> Reply:
                return await paywall.request(ctx, msg, name, sel)

            self._action_handlers[name] = request
            self._known_actions.add(name)
            return func

        return decorator

    async def charge(
        self, ctx: Context, msg: Inbound, product: str, sel: dict[str, Any] | None = None
    ) -> Reply:
        """Start the payment flow for a ``@paid`` product from your own code."""
        if self._paywall is None:
            raise ValueError(f"no @agent.paid product named {product!r}")
        return await self._paywall.request(ctx, msg, product, sel or {})

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #

    async def reply(self, ctx: Context, to: str, reply: Reply) -> None:
        """Send a reply (any handler return value) to ``to``."""
        for message in to_messages(reply):
            for content in message.content:
                if isinstance(content, MetadataContent) and "card_payload" in content.metadata:
                    self._known_actions |= collect_actions(
                        json.loads(content.metadata["card_payload"])
                    )
            await ctx.send(to, message)

    # ------------------------------------------------------------------ #
    # Protocol plumbing
    # ------------------------------------------------------------------ #

    async def _on_chat_ack(self, ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
        ctx.logger.debug(f"ack from {sender} for {msg.acknowledged_msg_id}")

    async def _on_chat_message(self, ctx: Context, sender: str, msg: ChatMessage) -> None:
        await ctx.send(
            sender,
            ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=msg.msg_id),
        )
        texts: list[str] = []
        metadata: dict[str, str] = {}
        for content in msg.content:
            if isinstance(content, TextContent):
                texts.append(content.text)
            elif isinstance(content, MetadataContent):
                metadata.update(content.metadata)
            elif isinstance(content, StartSessionContent):
                ctx.logger.info(f"session start from {sender}")
            elif isinstance(content, EndSessionContent):
                ctx.logger.info(f"session end from {sender}")
        raw_text = "\n".join(texts).strip()
        if not raw_text:
            return

        inbound = Inbound(
            sender=sender,
            text=strip_mention(raw_text),
            session=str(ctx.session),
            raw=msg,
            metadata=metadata,
            selection=parse_selection(raw_text, self._known_actions),
        )
        ctx.logger.info(f"<- {sender[:16]}…: {inbound.text[:200]!r}")
        try:
            reply = await self._dispatch(ctx, inbound)
        except Exception:
            ctx.logger.exception("handler failed")
            reply = self.error_message
        try:
            await self.reply(ctx, sender, reply)
        except Exception:
            ctx.logger.exception("could not send reply")
            await ctx.send(sender, text_message(self.error_message))

    async def _dispatch(self, ctx: Context, inbound: Inbound) -> Reply:
        action = inbound.action
        if action and action in self._action_handlers:
            return await _maybe_await(
                self._action_handlers[action](ctx, inbound, inbound.selection)
            )
        if self._text_handler is not None:
            return await _maybe_await(self._text_handler(ctx, inbound))
        return "Hi! This agent has no @agent.on_text handler yet."

    async def _auto_connect(self, ctx: Context) -> None:
        from .register import connect_mailbox

        if not os.getenv("AGENTVERSE_API_KEY"):
            ctx.logger.warning(
                "AGENTVERSE_API_KEY not set: open the inspector link above and click Connect "
                "(mailbox), or set the key so the agent connects itself."
            )
            return
        result = await connect_mailbox(self)
        if result.ok:
            ctx.logger.info(f"Connected to Agentverse as {result.profile_url}")
        else:
            ctx.logger.error(f"Agentverse connect failed: {result.detail}")
