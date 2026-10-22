from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fetch_hackkit import HackAgent, payments
from fetch_hackkit.payments import build_request, verify_fet_transfer
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RequestPayment,
)

USER = "agent1quser"
BUYER_WALLET = "fetch1buyer"


def test_build_request_testnet_defaults() -> None:
    req = build_request(
        amount="0.1", recipient_wallet="fetch1me", description="Brief", reference="r1"
    )
    assert req.accepted_funds[0] == Funds(amount="0.1", currency="FET", payment_method="fet_direct")
    assert req.metadata == {"fet_network": "stable-testnet", "provider_agent_wallet": "fetch1me"}
    assert req.reference == "r1"


def _ledger(monkeypatch: pytest.MonkeyPatch, events: dict | None, ok: bool = True) -> None:
    tx = None if events is None else SimpleNamespace(events=events, is_successful=lambda: ok)

    class FakeLedger:
        def __init__(self, _config) -> None: ...

        def query_tx(self, _tx_id):
            return tx

    monkeypatch.setattr("cosmpy.aerial.client.LedgerClient", FakeLedger)


def _events(amount: str, to: str = "fetch1me", sender: str = BUYER_WALLET) -> dict:
    return {"transfer": {"recipient": to, "sender": sender, "amount": amount}}


@pytest.mark.parametrize(
    ("events", "ok", "reason"),
    [
        (_events("100000000000000000atestfet"), True, "verified"),
        (_events("99999999999999999atestfet"), False, "amount"),
        (_events("100000000000000000atestfet", to="fetch1else"), False, "wallet"),
        (_events("100000000000000000atestfet", sender="fetch1thief"), False, "buyer"),
        (_events("100000000000000000afet"), False, "amount"),  # mainnet denom on testnet
        (None, False, "not found"),
    ],
)
def test_verify_fet_transfer(monkeypatch, events, ok, reason) -> None:
    _ledger(monkeypatch, events)
    result = verify_fet_transfer(
        transaction_id="tx", amount="0.1", recipient_wallet="fetch1me", sender_wallet=BUYER_WALLET
    )
    assert result[0] is ok and reason in result[1]


def _msg(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(UTC),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


@pytest.fixture
async def shop() -> HackAgent:
    agent = HackAgent("shop", mailbox=False, port=8996)

    @agent.paid("brief", amount="0.1", description="Project brief")
    async def brief(ctx, msg, sel):
        return f"brief for {sel.get('topic')}"

    return agent


async def test_paid_action_full_flow(shop: HackAgent, ctx, monkeypatch) -> None:
    assert shop._paywall is not None and shop._paywall.protocol.digest in shop.protocols
    await shop._on_chat_message(ctx, USER, _msg('{"action": "brief", "topic": "agents"}'))
    request = next(m for _, m in ctx.sent if isinstance(m, RequestPayment))
    assert request.recipient == str(shop.wallet.address())
    assert "0.1 testnet FET" in [m for _, m in ctx.sent if isinstance(m, ChatMessage)][0].text()

    monkeypatch.setattr(payments, "verify_fet_transfer", lambda **kw: (True, "verified"))
    commit = CommitPayment(
        funds=request.accepted_funds[0],
        recipient=request.recipient,
        transaction_id="tx1",
        reference=request.reference,
        metadata={"buyer_fet_wallet": BUYER_WALLET},
    )
    ctx.sent.clear()
    await shop._paywall._on_commit(ctx, USER, commit)
    assert isinstance(ctx.sent[0][1], CompletePayment)
    assert ctx.sent[1][1].text() == "brief for agents"

    # A replayed commit is acknowledged but does not deliver twice.
    ctx.sent.clear()
    await shop._paywall._on_commit(ctx, USER, commit)
    assert len(ctx.sent) == 1 and isinstance(ctx.sent[0][1], CompletePayment)


async def test_unverified_payment_is_cancelled(shop: HackAgent, ctx, monkeypatch) -> None:
    await shop._on_chat_message(ctx, USER, _msg('{"action": "brief"}'))
    request = next(m for _, m in ctx.sent if isinstance(m, RequestPayment))
    monkeypatch.setattr(payments, "verify_fet_transfer", lambda **kw: (False, "amount is too low"))
    ctx.sent.clear()
    commit = CommitPayment(
        funds=request.accepted_funds[0],
        recipient=request.recipient,
        transaction_id="tx2",
        reference=request.reference,
    )
    await shop._paywall._on_commit(ctx, USER, commit)
    assert isinstance(ctx.sent[0][1], CancelPayment)
    assert "couldn't verify" in ctx.sent[1][1].text()


async def test_commit_with_unknown_reference_or_wrong_sender(shop: HackAgent, ctx) -> None:
    await shop._on_chat_message(ctx, USER, _msg('{"action": "brief"}'))
    request = next(m for _, m in ctx.sent if isinstance(m, RequestPayment))
    ctx.sent.clear()
    commit = CommitPayment(
        funds=request.accepted_funds[0],
        recipient=request.recipient,
        transaction_id="tx3",
        reference=request.reference,
    )
    await shop._paywall._on_commit(ctx, "agent1qsomeoneelse", commit)
    assert isinstance(ctx.sent[0][1], CancelPayment)
