"""Agent Payment Protocol (seller side) with on-chain FET verification.

You normally use this through ``@agent.paid(...)``::

    @agent.paid("brief", amount="0.1", description="AI project brief")
    async def brief(ctx, msg, sel):
        return "Here is your brief..."

Flow (``uagents_core.contrib.protocols.payment``)::

    you  -> user : RequestPayment(accepted_funds=[0.1 FET], recipient=<agent wallet>, reference)
    user -> you  : CommitPayment(transaction_id, reference)      (or RejectPayment)
    you          : verify the transfer on-chain (cosmpy)
    you  -> user : CompletePayment(transaction_id) and the paid result
                   (or CancelPayment(reason) if verification fails)

Defaults to the Fetch.ai **stable testnet** (free test FET from the faucet).
Set ``FET_NETWORK=mainnet`` for real money.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from uagents import Context, Protocol
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

if TYPE_CHECKING:
    from .agent import ActionHandler, HackAgent, Inbound, Reply

FET_DECIMALS = 18
DEFAULT_DEADLINE_SECONDS = 600


def fet_network() -> str:
    """``stable-testnet`` (default) or ``mainnet``, from ``FET_NETWORK``."""
    return "mainnet" if os.getenv("FET_NETWORK", "").lower() == "mainnet" else "stable-testnet"


@dataclass
class Product:
    name: str
    amount: str
    currency: str
    description: str
    handler: ActionHandler


def build_request(
    *,
    amount: str,
    recipient_wallet: str,
    description: str,
    currency: str = "FET",
    reference: str | None = None,
    deadline_seconds: int = DEFAULT_DEADLINE_SECONDS,
    network: str | None = None,
) -> RequestPayment:
    """A ``RequestPayment`` for a direct FET transfer to ``recipient_wallet``."""
    network = network or fet_network()
    return RequestPayment(
        accepted_funds=[Funds(amount=amount, currency=currency, payment_method="fet_direct")],
        recipient=recipient_wallet,
        deadline_seconds=deadline_seconds,
        reference=reference or str(uuid4()),
        description=description,
        metadata={"fet_network": network, "provider_agent_wallet": recipient_wallet},
    )


def _amount_ok(amount: str, expected_base_units: int, denom: str) -> bool:
    if not amount.endswith(denom):
        return False
    try:
        return int(amount[: -len(denom)]) >= expected_base_units
    except ValueError:
        return False


def verify_fet_transfer(
    *,
    transaction_id: str,
    amount: str,
    recipient_wallet: str,
    sender_wallet: str | None = None,
    network: str | None = None,
) -> tuple[bool, str]:
    """Check on-chain that ``transaction_id`` sent at least ``amount`` FET to us.

    Blocking (network I/O): call it via ``asyncio.to_thread``.
    Returns ``(ok, reason)``.
    """
    from cosmpy.aerial.client import LedgerClient, NetworkConfig

    mainnet = (network or fet_network()) == "mainnet"
    denom = "afet" if mainnet else "atestfet"
    expected = int(Decimal(amount) * (10**FET_DECIMALS))
    config = NetworkConfig.fetchai_mainnet() if mainnet else NetworkConfig.fetchai_stable_testnet()
    try:
        tx = LedgerClient(config).query_tx(transaction_id)
    except Exception as exc:
        return False, f"transaction not found yet ({type(exc).__name__})"
    if tx is None:
        return False, "transaction not found"
    if hasattr(tx, "is_successful") and not tx.is_successful():
        return False, "transaction failed on-chain"
    events = getattr(tx, "events", None)
    if not isinstance(events, dict):
        return False, "transaction has no events"

    transfer = events.get("transfer") or {}
    received = events.get("coin_received") or {}
    spent = events.get("coin_spent") or {}
    to_us = recipient_wallet in (transfer.get("recipient"), received.get("receiver"))
    paid_enough = _amount_ok(str(transfer.get("amount", "")), expected, denom) or _amount_ok(
        str(received.get("amount", "")), expected, denom
    )
    from_buyer = sender_wallet is None or sender_wallet in (
        transfer.get("sender"),
        spent.get("spender"),
    )
    if not to_us:
        return False, "transfer was not to this agent's wallet"
    if not paid_enough:
        return False, f"amount is less than {amount} FET"
    if not from_buyer:
        return False, "transfer did not come from the buyer's wallet"
    return True, "verified"


class Paywall:
    """Seller-side payment protocol attached to a :class:`HackAgent`."""

    def __init__(self, agent: HackAgent) -> None:
        self.agent = agent
        self.products: dict[str, Product] = {}
        self.protocol = Protocol(spec=payment_protocol_spec, role="seller")
        self.protocol.on_message(CommitPayment)(self._on_commit)
        self.protocol.on_message(RejectPayment)(self._on_reject)
        agent.include(self.protocol, publish_manifest=True)

    @property
    def wallet(self) -> str:
        return str(self.agent.wallet.address())

    def add(self, product: Product) -> None:
        self.products[product.name] = product

    async def request(self, ctx: Context, msg: Inbound, name: str, sel: dict[str, Any]) -> Reply:
        product = self.products[name]
        reference = str(uuid4())
        ctx.storage.set(
            f"hackkit:pay:{reference}",
            {
                "product": name,
                "sender": msg.sender,
                "text": msg.text,
                "session": msg.session,
                "selection": sel,
                "expires": time.time() + DEFAULT_DEADLINE_SECONDS,
            },
        )
        await ctx.send(
            msg.sender,
            build_request(
                amount=product.amount,
                currency=product.currency,
                recipient_wallet=self.wallet,
                description=product.description,
                reference=reference,
            ),
        )
        net = "testnet " if fet_network() != "mainnet" else ""
        return (
            f"💳 **{product.description}** costs **{product.amount} {net}{product.currency}**. "
            "Approve the payment request to continue."
        )

    async def _on_reject(self, ctx: Context, sender: str, msg: RejectPayment) -> None:
        reason = f" ({msg.reason})" if msg.reason else ""
        await self.agent.reply(ctx, sender, f"No problem, payment cancelled{reason}.")

    async def _on_commit(self, ctx: Context, sender: str, msg: CommitPayment) -> None:
        from .agent import Inbound, text_message

        tx = msg.transaction_id
        key = f"hackkit:pay:{msg.reference}"
        pending = ctx.storage.get(key) if msg.reference else None
        if ctx.storage.get(f"hackkit:paid-tx:{tx}"):
            await ctx.send(sender, CompletePayment(transaction_id=tx))  # duplicate commit
            return
        if not isinstance(pending, dict) or pending.get("sender") != sender:
            await ctx.send(
                sender, CancelPayment(transaction_id=tx, reason="Unknown payment reference")
            )
            return
        if time.time() > float(pending.get("expires", 0)):
            ctx.storage.remove(key)
            await ctx.send(
                sender, CancelPayment(transaction_id=tx, reason="Payment request expired")
            )
            await self.agent.reply(ctx, sender, "That payment request expired. Please try again.")
            return
        product = self.products.get(str(pending["product"]))
        if product is None:
            await ctx.send(sender, CancelPayment(transaction_id=tx, reason="Unknown product"))
            return

        buyer = (msg.metadata or {}).get("buyer_fet_wallet") or (msg.metadata or {}).get(
            "buyer_fet_address"
        )
        ok, reason = False, "not verified"
        for attempt in range(3):  # the tx may take a few seconds to be indexed
            ok, reason = await asyncio.to_thread(
                verify_fet_transfer,
                transaction_id=tx,
                amount=product.amount,
                recipient_wallet=self.wallet,
                sender_wallet=buyer if isinstance(buyer, str) else None,
            )
            if ok or "not found" not in reason:
                break
            await asyncio.sleep(3 * (attempt + 1))
        if not ok:
            ctx.logger.warning(f"payment {tx} rejected: {reason}")
            await ctx.send(sender, CancelPayment(transaction_id=tx, reason=reason))
            await self.agent.reply(ctx, sender, f"I couldn't verify that payment: {reason}.")
            return

        ctx.storage.set(f"hackkit:paid-tx:{tx}", True)
        ctx.storage.remove(key)
        await ctx.send(sender, CompletePayment(transaction_id=tx))
        ctx.logger.info(f"payment {tx} verified for {product.name}")

        inbound = Inbound(
            sender=sender,
            text=str(pending.get("text", "")),
            session=str(pending.get("session", "")),
            raw=text_message(str(pending.get("text", ""))),
            selection=dict(pending.get("selection") or {}),
        )
        try:
            reply = await product.handler(ctx, inbound, inbound.selection)
        except Exception:
            ctx.logger.exception("paid handler failed")
            reply = (
                "Payment received, but something failed while preparing your result. "
                f"Please contact the agent owner with transaction id {tx}."
            )
        await self.agent.reply(ctx, sender, reply)
