"""Use any remote MCP server's tools from your agent (``pip install fetch-hackkit[mcp]``).

    tools = await mcp_tools("https://mcp.deepwiki.com/mcp")
    answer = await ASI1().run_tools("How do uAgents handle mailboxes?", tools=tools)

Each tool call opens a short-lived connection, so there is nothing to keep
alive or clean up. To go the other way (publish an MCP server *as* an agent
on Agentverse), use ``uagents-adapter[mcp]``'s ``MCPServerAdapter``.
"""

from __future__ import annotations

import logging
from typing import Any

from .asi1 import Tool

try:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
except ImportError as exc:  # pragma: no cover
    raise ImportError("MCP support needs the extra: pip install 'fetch-hackkit[mcp]'") from exc

# The MCP transport logs every HTTP request at INFO; keep agent logs readable.
logging.getLogger("httpx2").setLevel(logging.WARNING)


def _client(url: str, headers: dict[str, str] | None) -> Client:
    if not headers:
        return Client(url)
    http = httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30.0, read=300.0))
    return Client(streamable_http_client(url, http_client=http))


def _result_text(result: Any) -> Any:
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    parts = [getattr(block, "text", None) or str(block) for block in result.content or []]
    text = "\n".join(p for p in parts if p)
    if getattr(result, "is_error", False):
        return {"error": text or "tool failed"}
    return text


async def call_mcp_tool(
    url: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    """Call one tool on a remote MCP server and return its text/structured result."""
    async with _client(url, headers) as client:
        return _result_text(await client.call_tool(name, arguments or {}))


async def mcp_tools(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    include: set[str] | None = None,
    prefix: str = "",
) -> list[Tool]:
    """List a server's tools as :class:`~fetch_hackkit.asi1.Tool` objects for ``run_tools``.

    Args:
        url: Streamable-HTTP MCP endpoint, e.g. ``https://mcp.deepwiki.com/mcp``.
        headers: Extra HTTP headers, e.g. ``{"Authorization": "Bearer ..."}``.
        include: Only expose these tool names (keeps the model focused).
        prefix: Prepended to tool names to avoid clashes between servers.
    """
    async with _client(url, headers) as client:
        listed = await client.list_tools()

    tools: list[Tool] = []
    for spec in listed.tools:
        if include and spec.name not in include:
            continue

        async def call(arguments: dict[str, Any], _name: str = spec.name) -> Any:
            return await call_mcp_tool(url, _name, arguments, headers=headers)

        schema = dict(spec.input_schema or {"type": "object", "properties": {}})
        tools.append(
            Tool(
                name=f"{prefix}{spec.name}",
                description=spec.description or spec.name,
                parameters=schema,
                call=call,
            )
        )
    return tools
