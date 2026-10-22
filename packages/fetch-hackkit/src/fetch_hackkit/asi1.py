"""ASI:One LLM client: chat, structured output, and a tool-calling loop.

ASI:One speaks the OpenAI Chat Completions format, so this wraps the official
``openai`` SDK pointed at ``https://api.asi1.ai/v1``.

    llm = ASI1()                                   # reads ASI_ONE_API_KEY
    text = await llm.ask("Explain uAgents in one line")
    answer = await llm.run_tools("Weather in Paris?", tools=[get_weather])

Any plain Python function (sync or async) with type hints and a docstring can
be a tool; its JSON schema is generated for you.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast, get_type_hints

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError, create_model

ASI1_BASE_URL = "https://api.asi1.ai/v1"
DEFAULT_MODEL = "asi1"
_KEY_ENVS = ("ASI_ONE_API_KEY", "ASI1_API_KEY")

log = logging.getLogger("fetch_hackkit.asi1")
M = TypeVar("M", bound=BaseModel)
Message = dict[str, Any]


class ASI1Error(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@dataclass
class Tool:
    """A function the model may call."""

    name: str
    description: str
    parameters: dict[str, Any]
    call: Callable[[dict[str, Any]], Awaitable[Any]]

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _doc_parts(func: Callable[..., Any]) -> tuple[str, dict[str, str]]:
    """Summary + per-argument descriptions from a Google-style docstring."""
    doc = inspect.getdoc(func) or ""
    summary = doc.split("\n\n", 1)[0].strip().replace("\n", " ")
    args: dict[str, str] = {}
    match = re.search(r"^(?:Args|Arguments|Parameters):\s*\n(.*?)(?:\n\S|\Z)", doc, re.S | re.M)
    if match:
        for line in match.group(1).splitlines():
            m = re.match(r"\s+(\w+)(?:\s*\([^)]*\))?:\s*(.+)", line)
            if m:
                args[m.group(1)] = m.group(2).strip()
    return summary or func.__name__.replace("_", " "), args


def tool(func: Callable[..., Any], *, name: str | None = None) -> Tool:
    """Turn a typed Python function (sync or async) into a :class:`Tool`."""
    if isinstance(func, Tool):
        return func
    summary, arg_docs = _doc_parts(func)
    hints = get_type_hints(func)
    fields: dict[str, Any] = {}
    for pname, param in inspect.signature(func).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = hints.get(pname, str)
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[pname] = (annotation, default)
    model = create_model(f"{func.__name__}_args", **fields)
    schema = model.model_json_schema()
    schema.pop("title", None)
    for pname, prop in schema.get("properties", {}).items():
        prop.pop("title", None)
        if pname in arg_docs:
            prop["description"] = arg_docs[pname]

    async def call(arguments: dict[str, Any]) -> Any:
        validated = model.model_validate(arguments)
        kwargs = {k: getattr(validated, k) for k in fields}
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return await asyncio.to_thread(func, **kwargs)

    return Tool(name=name or func.__name__, description=summary, parameters=schema, call=call)


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a reply that may wrap it in prose or code fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class ASI1:
    """Thin async ASI:One client."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        base_url: str = ASI1_BASE_URL,
        timeout: float = 60.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model or os.getenv("ASI_ONE_MODEL") or DEFAULT_MODEL
        if client is not None:
            self.client = client
            return
        key = api_key or next((os.environ[k] for k in _KEY_ENVS if os.getenv(k)), None)
        if not key:
            raise ASI1Error(
                "ASI_ONE_API_KEY is not set. Get a key at https://asi1.ai/developer "
                "and put it in your .env."
            )
        self.client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=timeout)

    async def chat(
        self, messages: Sequence[Message], *, model: str | None = None, **kwargs: Any
    ) -> str:
        """One completion. Returns the assistant text."""
        resp = await self.client.chat.completions.create(
            model=model or self.model,
            messages=cast(Any, list(messages)),
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def ask(
        self, prompt: str, *, system: str | None = None, history: Sequence[Message] = ()
    ) -> str:
        """Ask a single question (optionally with a system prompt and prior turns)."""
        return await self.chat(_messages(prompt, system, history))

    async def structured(
        self, prompt: str, schema: type[M], *, system: str | None = None, retries: int = 1
    ) -> M:
        """Ask for JSON matching a Pydantic model; validated, with one repair retry."""
        instructions = (
            "Reply with only a JSON object matching this JSON schema, no prose:\n"
            + json.dumps(schema.model_json_schema())
        )
        messages = _messages(prompt, f"{system}\n\n{instructions}" if system else instructions)
        for attempt in range(retries + 1):
            text = await self.chat(messages)
            try:
                return schema.model_validate_json(_extract_json(text))
            except ValidationError as exc:
                if attempt == retries:
                    raise ASI1Error(f"model did not return valid {schema.__name__}: {exc}") from exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That was invalid: {exc}. Try again."},
                ]
        raise AssertionError("unreachable")

    async def run_tools(
        self,
        prompt: str | Sequence[Message],
        tools: Sequence[Callable[..., Any] | Tool],
        *,
        system: str | None = None,
        max_steps: int = 6,
        on_call: Callable[[str, dict[str, Any], Any], None] | None = None,
    ) -> str:
        """Let the model call ``tools`` until it can answer; returns the final text.

        Tool exceptions are sent back to the model as ``{"error": ...}`` so it
        can retry or explain, instead of crashing your agent.
        """
        registry = {t.name: t for t in (f if isinstance(f, Tool) else tool(f) for f in tools)}
        specs = [t.spec() for t in registry.values()]
        messages: list[Message] = (
            _messages(prompt, system)
            if isinstance(prompt, str)
            else [*([{"role": "system", "content": system}] if system else []), *prompt]
        )
        for _ in range(max_steps):
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=cast(Any, messages),
                tools=cast(Any, specs),
            )
            message = resp.choices[0].message
            calls: list[Any] = list(message.tool_calls or [])
            if not calls:
                return message.content or ""
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.function.name,
                                "arguments": c.function.arguments,
                            },
                        }
                        for c in calls
                        if getattr(c, "function", None) is not None
                    ],
                }
            )
            for call in calls:
                fn = getattr(call, "function", None)
                name = getattr(fn, "name", "")
                args: dict[str, Any] = {}
                try:
                    args = json.loads(getattr(fn, "arguments", None) or "{}")
                    if name not in registry:
                        raise ASI1Error(f"unknown tool {name!r}")
                    result: Any = await registry[name].call(args)
                except Exception as exc:  # report to the model, keep going
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                    log.warning("tool %s failed: %s", name, exc)
                if on_call:
                    on_call(name, args, result)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": _to_text(result)[:20_000]}
                )
        messages.append(
            {"role": "user", "content": "Stop calling tools and answer with what you have."}
        )
        return await self.chat(messages)


def _messages(
    prompt: str, system: str | None = None, history: Sequence[Message] = ()
) -> list[Message]:
    out: list[Message] = [{"role": "system", "content": system}] if system else []
    return [*out, *history, {"role": "user", "content": prompt}]


# --------------------------------------------------------------------------- #
# Per-conversation memory (ASI:One sends your agent one message at a time)
# --------------------------------------------------------------------------- #


def history(ctx: Any, session: str) -> list[Message]:
    """Prior turns for this conversation, stored in ``ctx.storage``."""
    stored = ctx.storage.get(f"hackkit:history:{session}")
    return list(stored) if isinstance(stored, list) else []


def remember(ctx: Any, session: str, role: str, content: str, *, keep: int = 20) -> None:
    """Append a turn to this conversation's history (keeps the last ``keep``)."""
    turns = [*history(ctx, session), {"role": role, "content": content}][-keep:]
    ctx.storage.set(f"hackkit:history:{session}", turns)
