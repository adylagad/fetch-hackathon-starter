"""Agentverse registration: mailbox connect, endpoint registration, profile lookup.

Where each profile field is set:

==================  =====================================  =========================
Field               Set in code (this module / HackAgent)  Agentverse MCP tool
==================  =====================================  =========================
name                ``HackAgent(name=...)``                ``update_user_agent``
@handle             ``HackAgent(handle=...)``              *not available*
short description   ``HackAgent(description=...)``         ``update_user_agent``
README              ``HackAgent(readme_path=...)``         ``update_user_agent``
avatar              ``HackAgent(avatar_url=...)``          ``update_user_agent``
==================  =====================================  =========================

The ``@handle`` is unique across Agentverse (max 40 chars). If it is taken,
registration fails with HTTP 409.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from uagents import Agent

HANDLE_MAX_LEN = 40
_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
AGENTVERSE_URL = "https://agentverse.ai"


def validate_handle(handle: str) -> str:
    """Check an Agentverse ``@handle`` locally and return it without a leading ``@``."""
    value = handle.removeprefix("@")
    if not value or len(value) > HANDLE_MAX_LEN:
        raise ValueError(f"handle must be 1-{HANDLE_MAX_LEN} characters, got {len(value)}")
    if not _HANDLE_RE.match(value):
        raise ValueError(
            f"handle {handle!r} may only contain letters, digits, '-', '_' and '.' (no spaces)"
        )
    return value


def profile_url(address: str) -> str:
    return f"{AGENTVERSE_URL}/agents/details/{address}/profile"


def _api_key(api_key: str | None) -> str:
    key = api_key or os.getenv("AGENTVERSE_API_KEY")
    if not key:
        raise ValueError(
            "AGENTVERSE_API_KEY is not set. Create one at https://agentverse.ai/profile/api-keys"
        )
    return key


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        detail = resp.text
    hint = ""
    if resp.status_code == 401:
        hint = " (invalid or expired AGENTVERSE_API_KEY)"
    elif resp.status_code == 409:
        hint = " (address or @handle already registered by another account; pick another handle)"
    return f"HTTP {resp.status_code}{hint}: {detail}"


@dataclass
class ConnectResult:
    ok: bool
    detail: str = ""
    address: str = ""

    @property
    def profile_url(self) -> str:
        return profile_url(self.address)


def _registration_body(agent: Agent, endpoint: str | None) -> str:
    """The same ``RegistrationRequest`` the inspector's Connect button sends."""
    from uagents_core.registration import RegistrationRequest

    request = RegistrationRequest(
        address=agent.address,
        name=agent.name,
        handle=agent._handle,
        url=endpoint,
        profile=agent._build_registration_profile(),
        endpoints=agent._endpoints,
        protocols=list(agent.protocols.keys()),
        metadata=agent.metadata,
    )
    return request.model_dump_json()


async def connect_mailbox(
    agent: Agent,
    *,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: float = 15.0,
) -> ConnectResult:
    """Do what the inspector's *Connect* button does, using ``AGENTVERSE_API_KEY``.

    Proves the agent owns its address (signed challenge), then publishes its
    profile (name, @handle, description, README, protocols) to Agentverse.
    For an agent with its own public URL, use :func:`register_endpoint_agent`.
    """
    key = _api_key(api_key)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    av = agent._agentverse
    identity = agent._identity
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        try:
            resp = await client.get(f"{av.identity_api}/{identity.address}/challenge")
            if resp.status_code != 200:
                return ConnectResult(False, "challenge: " + _detail(resp), agent.address)
            challenge = resp.json()["challenge"]
            proof = {
                "address": identity.address,
                "challenge": challenge,
                "challenge_response": identity.sign(challenge.encode()),
            }
            resp = await client.post(av.identity_api, json=proof)
            if resp.status_code != 200:
                return ConnectResult(False, "identity proof: " + _detail(resp), agent.address)
            resp = await client.post(av.agents_api, content=_registration_body(agent, endpoint))
            if resp.status_code not in (200, 201):
                return ConnectResult(False, "register: " + _detail(resp), agent.address)
        except httpx.HTTPError as exc:
            return ConnectResult(False, f"network error: {exc}", agent.address)
    return ConnectResult(True, "", agent.address)


def register_endpoint_agent(agent: Agent, endpoint: str, *, api_key: str | None = None) -> bool:
    """Register an agent that runs at a public URL (Render, Fly, a VM, ...).

    Uses ``uagents_core``'s ``register_agent`` (which, unlike ``register_chat_agent``,
    accepts a ``handle``). Raises ``AgentverseRequestError`` on failure.
    """
    from uagents_core.config import AgentverseConfig
    from uagents_core.utils.registration import (
        AgentverseRegistrationRequest,
        RegistrationRequestCredentials,
        register_agent,
    )

    profile = agent._build_registration_profile()
    request = AgentverseRegistrationRequest(
        name=agent.name,
        endpoint=endpoint,
        protocols=list(agent.protocols.keys()),
        description=profile.description or None,
        readme=profile.readme or None,
        avatar_url=profile.avatar_url or None,
        handle=agent._handle,
        active=True,
    )
    seed = os.getenv("AGENT_SEED_PHRASE")
    if not seed:
        raise ValueError("AGENT_SEED_PHRASE is not set")
    return register_agent(
        request,
        AgentverseConfig(),
        RegistrationRequestCredentials(
            agentverse_api_key=_api_key(api_key), agent_seed_phrase=seed
        ),
    )


def lookup_agent(address: str, *, api_key: str | None = None) -> dict[str, Any] | None:
    """Your Agentverse record for ``address`` (``None`` if it is not on your account)."""
    resp = httpx.get(
        f"{AGENTVERSE_URL}/v2/agents/{address}",
        headers={"Authorization": f"Bearer {_api_key(api_key)}"},
        timeout=15.0,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise RuntimeError(_detail(resp))
    data = resp.json()
    return data if isinstance(data, dict) else None


def resolve(identifier: str) -> dict[str, Any] | None:
    """Public Almanac lookup by address, ``@handle`` or domain; ``None`` if unassigned.

    Returns ``{"address", "status", "type", "protocols", "endpoints", "expiry", ...}``.
    """
    ident = identifier.removeprefix("@")
    resp = httpx.get(f"{AGENTVERSE_URL}/v2/almanac/resolve/{ident}", timeout=15.0)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise RuntimeError(_detail(resp))
    data = resp.json()
    return data if isinstance(data, dict) else None


def handle_available(handle: str, *, mine: str | None = None) -> bool:
    """True if nobody (other than address ``mine``) has taken ``handle``."""
    record = resolve(validate_handle(handle))
    return record is None or (mine is not None and record.get("address") == mine)


def resolve_address(identifier: str) -> str:
    """``agent1...`` passes through; ``@handle``/domain is looked up on the Almanac."""
    if identifier.startswith(("agent1", "test-agent1")):
        return identifier
    record = resolve(identifier)
    if not record or not record.get("address"):
        raise ValueError(f"no agent found for {identifier!r}")
    return str(record["address"])
