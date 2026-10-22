"""Pre-submission checks: ``hackkit doctor``.

Each check maps to a hackathon requirement (registered, discoverable via
ASI:One, chat protocol, README with badges + address) and says how to fix it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .register import lookup_agent, profile_url, resolve

CHAT_PROTOCOL_DIGEST = "30a801ed3a83f9a0ff0a9f1e6fe958cb91da1fc2218b153df7b6cbf87bd33d62"
BADGES = (
    "![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)",
    "![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)",
)


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str = ""
    fix: str = ""

    @property
    def icon(self) -> str:
        return {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[self.status]


def identity_from_seed(seed: str) -> tuple[str, str]:
    """``(agent address, FET wallet address)`` for a seed, exactly as uAgents derives them."""
    from cosmpy.aerial.wallet import LocalWallet
    from cosmpy.crypto.keypairs import PrivateKey
    from uagents.config import LEDGER_PREFIX
    from uagents_core.identity import Identity, derive_key_from_seed

    address = Identity.from_seed(seed, 0).address
    wallet = LocalWallet(
        PrivateKey(derive_key_from_seed(seed, LEDGER_PREFIX, 0)), prefix=LEDGER_PREFIX
    )
    return address, str(wallet.address())


def check_seed() -> tuple[Check, str | None]:
    seed = os.getenv("AGENT_SEED_PHRASE", "")
    if not seed:
        return Check(
            "Seed phrase",
            "fail",
            "AGENT_SEED_PHRASE is not set",
            "Run `hackkit seed` and put the phrase in .env",
        ), None
    if len(seed) < 24:
        return Check(
            "Seed phrase",
            "warn",
            "seed is short; anyone who guesses it owns your agent",
            "Use `hackkit seed` for a long random phrase",
        ), identity_from_seed(seed)[0]
    address, wallet = identity_from_seed(seed)
    return Check("Seed phrase", "ok", f"address {address}\n      wallet  {wallet}"), address


def check_asi1() -> Check:
    key = os.getenv("ASI_ONE_API_KEY") or os.getenv("ASI1_API_KEY")
    if not key:
        return Check(
            "ASI:One API key",
            "warn",
            "ASI_ONE_API_KEY is not set",
            "Get one at https://asi1.ai/developer (only needed if you call the LLM)",
        )
    try:
        resp = httpx.post(
            "https://api.asi1.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("ASI_ONE_MODEL", "asi1"),
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return Check("ASI:One API key", "warn", f"could not reach ASI:One: {exc}")
    if resp.status_code in (401, 403):
        return Check(
            "ASI:One API key",
            "fail",
            "key rejected",
            "Create a new key at https://asi1.ai/developer",
        )
    if resp.status_code >= 400:
        return Check("ASI:One API key", "warn", f"HTTP {resp.status_code}: {resp.text[:200]}")
    return Check("ASI:One API key", "ok", "key works")


def check_registration(address: str) -> Check:
    if not os.getenv("AGENTVERSE_API_KEY"):
        return Check(
            "Agentverse account",
            "warn",
            "AGENTVERSE_API_KEY is not set (cannot check)",
            "Create one at https://agentverse.ai/profile/api-keys",
        )
    try:
        record = lookup_agent(address)
    except RuntimeError as exc:
        return Check("Agentverse account", "fail", str(exc))
    if record is None:
        return Check(
            "Agentverse account",
            "fail",
            "agent is not on your Agentverse account",
            "Run the agent with AGENTVERSE_API_KEY set (auto-connect), or open the "
            "inspector link and click Connect -> Mailbox",
        )
    return Check("Agentverse account", "ok", profile_url(address))


def check_almanac(address: str) -> Check:
    try:
        record = resolve(address)
    except (RuntimeError, httpx.HTTPError) as exc:
        return Check("Almanac / ASI:One discoverability", "warn", f"lookup failed: {exc}")
    if record is None:
        return Check(
            "Almanac / ASI:One discoverability",
            "fail",
            "agent is not on the Almanac",
            "Start the agent and connect it to Agentverse (mailbox)",
        )
    problems = []
    if record.get("status") != "active":
        problems.append(f"status is {record.get('status')!r} (start the agent)")
    if CHAT_PROTOCOL_DIGEST not in (record.get("protocols") or []):
        problems.append("chat protocol not published (include it with publish_manifest=True)")
    expiry = record.get("expiry")
    if expiry:
        when = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        if when < datetime.now(UTC):
            problems.append("registration expired (restart the agent)")
    if problems:
        return Check("Almanac / ASI:One discoverability", "fail", "; ".join(problems))
    return Check(
        "Almanac / ASI:One discoverability",
        "ok",
        f"active, chat protocol published, type {record.get('type')}",
    )


def check_handle(handle: str, address: str) -> Check:
    try:
        record = resolve(handle)
    except (RuntimeError, httpx.HTTPError) as exc:
        return Check("@handle", "warn", f"lookup failed: {exc}")
    if record is None:
        return Check(
            "@handle",
            "fail",
            f"@{handle} is not assigned yet",
            "Pass handle=... to HackAgent and reconnect to Agentverse",
        )
    if record.get("address") != address:
        return Check(
            "@handle", "fail", f"@{handle} belongs to another agent", "Choose a different handle"
        )
    return Check("@handle", "ok", f"@{handle} -> this agent")


def check_readme(path: Path, address: str | None) -> Check:
    if not path.exists():
        return Check("README", "fail", f"{path} not found", "Your repo needs a README")
    text = path.read_text(encoding="utf-8")
    missing = [b for b in BADGES if b not in text]
    problems = []
    if missing:
        problems.append("missing badge(s): " + ", ".join(b.split("]")[0][2:] for b in missing))
    if address and address not in text:
        problems.append("agent address not listed")
    if problems:
        return Check(
            "README",
            "fail",
            "; ".join(problems),
            "Add the innovationlab + hackathon badges and your agent name + address",
        )
    return Check("README", "ok", "badges and address present")


def run(*, readme: Path, handle: str | None) -> list[Check]:
    checks: list[Check] = []
    seed_check, address = check_seed()
    checks.append(seed_check)
    checks.append(check_asi1())
    if address:
        checks.append(check_registration(address))
        checks.append(check_almanac(address))
        if handle:
            checks.append(check_handle(handle.removeprefix("@"), address))
    checks.append(check_readme(readme, address))
    return checks
