# AGENTS.md

Guide for AI coding agents (opencode, Claude Code, Cursor, Codex, and others) working in this repo. Humans: this is also the fastest complete reference.

You are helping a hackathon team build a **Fetch.ai agent**. To win, the agent must:
- be registered on **Agentverse**;
- be discoverable and usable inside **ASI:One** chat (the Agent Chat Protocol);
- do real work: tools, APIs, MCP, or other agents;
- ideally use **interactive cards** and the **Payment Protocol**.

`fetch-hackkit` (in `packages/fetch-hackkit`) does the plumbing. Write agent code against it.

## Repo map

| Path | What it is |
|---|---|
| `packages/fetch-hackkit/src/fetch_hackkit/` | The library: `agent.py` (HackAgent), `cards.py`, `asi1.py`, `payments.py`, `mcp.py`, `peers.py`, `register.py`, `doctor.py`, `cli.py` |
| `agent/agent.py` | Showcase agent entry point. **Edit this (or copy it) to build your agent.** |
| `agent/flows/*.py` | One feature per file. Each has `register(agent)`. Delete what you don't need. |
| `agent/peer/agent.py` | A second, minimal agent for multi-agent demos |
| `agent/README.md` | The README Agentverse shows on your profile. ASI:One reads it to route users to you. |
| `agent/.env.example` | Every environment variable, documented |

## Golden rules

1. **Use `HackAgent`, not a bare `uagents.Agent`.** It includes the chat protocol, publishes its manifest, sends acknowledgements, and turns handler exceptions into a friendly reply.
2. **Handlers return replies; they don't call `ctx.send` for chat.** Return a `str`, a `cards.Card`, a `ChatMessage`, or a list of these.
3. **Never block the event loop.** Use `httpx.AsyncClient` / `async` SDKs. Wrap blocking calls in `await asyncio.to_thread(fn, ...)`.
4. **Secrets live in `.env`** (gitignored): `AGENT_SEED_PHRASE`, `ASI_ONE_API_KEY`, `AGENTVERSE_API_KEY`.
   - Never hard-code them. Never print the seed.
   - The seed *is* the agent: the same seed always gives the same address and wallet.
5. **Keep per-conversation state in `ctx.storage`, keyed by `msg.session`.** ASI:One sends your agent one message at a time.
6. **Every card has a narration.** It's the fallback text if a card fails to render.
7. **Run `uv run pytest -q` and `uv run ruff check .` after changes.**

## Commands

```bash
uv sync --all-packages                 # install everything (Python 3.11-3.14)
cd agent && cp .env.example .env       # then fill it in
uv run hackkit seed                    # generate AGENT_SEED_PHRASE (+ shows address and wallet)
uv run hackkit handle my-agent         # is @my-agent free on Agentverse?
uv run python agent.py                 # run the agent (from agent/)
uv run hackkit whoami                  # address, wallet, Agentverse profile URL
uv run hackkit doctor --readme README.md   # pre-submission checks
uv run pytest -q && uv run ruff check . && uv run mypy   # from repo root
```

## The agent pattern

```python
from fetch_hackkit import HackAgent, cards

agent = HackAgent(
    name="Trip Planner",                 # display name on Agentverse
    handle="trip-planner",               # @handle: unique, <= 40 chars
    description="Plans weekend trips with live prices.",   # short description
    readme_path="README.md",             # long description (ASI:One routing reads it)
)

@agent.on_text                           # free text (leading @mentions already stripped)
async def on_text(ctx, msg):             # msg: Inbound(sender, text, session, selection, raw)
    return cards.carousel("Pick a city", [
        cards.item("sf", "San Francisco", action="pick_city"),
        cards.item("la", "Los Angeles", action="pick_city"),
    ], narration="Where to?")

@agent.on_action("pick_city")            # card taps, routed by selection["action"]
async def pick_city(ctx, msg, sel):      # sel == {"action": "pick_city", "id": "sf"}
    return f"Planning a trip to {sel['id']}..."

if __name__ == "__main__":
    agent.run()
```

`HackAgent` subclasses `uagents.Agent`, so `@agent.on_interval(period=60)`, `@agent.on_event("startup")`, `agent.include(protocol)` and `ctx.storage` all work.

## Interactive cards (ASI:One UI)

A card is a chat message with narration text plus a `MetadataContent` declaration. ASI:One renders it as UI. When the user taps a button, the button's **selection** comes back to your agent as a message.

### Pick the right card

| Card | Use for | Builder |
|---|---|---|
| `carousel` | Menus, search results, options (one button per item) | `cards.carousel(title, [cards.item(id, title, action=...)])` |
| `detail` | One thing in depth: image, key/value rows, radio choice, several buttons | `cards.detail(title, rows={...}, ctas=[cards.cta(...)], sub_options=cards.radio(...))` |
| `form` | Collect input (`text`, `number`, `email`, `select`, `checkbox`) | `cards.form(title, [cards.field(...)], submit=cards.cta(...))` |
| `review` | Confirm before anything irreversible (payment, booking, sending) | `cards.review(title, rows=..., approve=cards.cta(...), reject=cards.cta(...))` |
| `custom` | Anything else, built from primitives | `cards.custom(ui.section(title, [ui.text(...), ui.button(...)]))` |
| read-only | Show a result that needs no input | `cards.info(title, rows=...)` |

Custom primitives live in `fetch_hackkit.cards.ui`:
- **Layout:** `section`, `group(direction="row"|"column")`, `divider`.
- **Content:** `text(style=)`, `heading(level=)`, `image`, `badge(variant="info"|"success"|"warning")`.
- **Interactive:** `button`, `input`, `list_items` + `list_item`, `choice_grid` (image picker).

### Selections: what comes back

Every button built with `cards.cta(label, action, **data)`, `cards.item(..., action=...)` or `ui.button(label, action, **data)` sends `{"action": action, **data}`. The values that come back depend on the card:

| Card | What arrives |
|---|---|
| carousel item | `{"action", "id", ...data}` |
| detail | the button's selection, plus the radio value under `sub_options.name` |
| form | the submit button's selection, plus **every field value** keyed by field name |
| review | the approve or the reject selection |
| custom | the button's selection, plus every `input` / `choice_grid` value keyed by `name` |

It arrives in one of two formats, and `HackAgent` handles both:
- **Direct @mention:** JSON. `sel` is the full dict.
- **Routed by the ASI:One planner:** a prose sentence containing the selection's identifiers. `HackAgent` finds the action word and gives you `{"action": ..., "prose": "<sentence>"}`. Field values may only be inside `msg.text`.

Design rules that follow:
- **Make `action` names distinctive tokens** (`book_hotel`, not `ok`) so they can be found in prose.
- **For important values, check `"prose" in sel`** and either recover them from `msg.text` or ask again.
- **Unique ids in `data`** (e.g. `id="trip_42"`) also appear in the prose.
- **One active card:** pass `card_id=` to `Card.to_message(card_id=...)` (or `cards.card_message`), and ignore taps whose `sel.get("card_id")` isn't the latest one.

### Limits (enforced by `cards.validate`, which raises `CardError`)
- Payload of 64 KB or less (the kit aims for under 60 KB).
- Custom trees at most 8 levels deep.
- `select` fields need `options`.
- Only these card kinds exist; there is no standalone "buttons" kind. Use `custom` with `ui.button`.

If ASI:One rejects a card, the user sees only the narration. That's why every card needs one.

## ASI:One LLM (`fetch_hackkit.asi1`)

The API is OpenAI-compatible (`https://api.asi1.ai/v1`). Models: `asi1` (default), `asi1-ultra`, `asi1-mini`. Set `ASI_ONE_MODEL` to switch.

```python
from fetch_hackkit import ASI1, history, remember

llm = ASI1()                                        # raises ASI1Error if no key
text = await llm.ask("Summarise this", system="Be brief")
plan = await llm.structured("Plan a trip to SF", TripPlan)   # Pydantic model, validated
answer = await llm.run_tools(question, tools=[get_weather, search_flights])
```

- **Tools are plain functions,** sync or async, with type hints and a docstring. Google-style `Args:` lines become parameter descriptions.
- **Failures don't crash the agent:** a tool exception goes back to the model as `{"error": ...}`.
- **Use `run_tools`** to make the agent *act*, not just chat. Judges penalise "a thin wrapper around an API".
- **Multi-turn memory:** `history(ctx, msg.session)` and `remember(ctx, msg.session, role, text)`.

## Payments (`@agent.paid`)

```python
@agent.paid("premium_report", amount="0.5", description="Premium market report")
async def premium(ctx, msg, sel):      # runs only after payment is verified on-chain
    return await build_report(sel)
```

1. A tap with `action="premium_report"`, or `await agent.charge(ctx, msg, "premium_report")`, sends `RequestPayment` (FET, `fet_direct`, the agent's wallet as recipient).
2. The user approves in ASI:One. The agent receives `CommitPayment(transaction_id)`.
3. The kit verifies the transfer on-chain (recipient, amount, buyer) with cosmpy, retrying while the transaction indexes. It then sends `CompletePayment` and runs your handler. Otherwise it sends `CancelPayment(reason)`.
4. Replayed commits are acknowledged but never delivered twice.

Notes:
- **Network:** stable testnet by default (`FET_NETWORK=mainnet` for real FET). Test FET is free from the Fetch.ai testnet faucet.
- **Show the price first:** put a `review` card before an expensive paid action.
- **Never deliver paid work before the handler runs.**

## MCP

**Use an MCP server's tools inside your agent:**
```python
from fetch_hackkit.mcp import mcp_tools, call_mcp_tool
tools = await mcp_tools("https://mcp.deepwiki.com/mcp", include={"ask_wiki_question"})
answer = await ASI1().run_tools("How does X work in fetchai/uAgents?", tools=tools)
```
Pass `headers={"Authorization": "Bearer ..."}` for authenticated servers.

**Publish an MCP server as an Agentverse agent:** use `uagents-adapter[mcp]` (`MCPServerAdapter`). It's not part of this kit.

## Multi-agent

```python
from fetch_hackkit.peers import ask_agent, PeerError
reply = await ask_agent(ctx, "@some-handle", "question", timeout=60)  # or an agent1... address
```

`ask_agent` works with any chat-protocol agent on Agentverse. `agent/peer/agent.py` is a template for your own specialist agent. Run it, then set `PEER_AGENT` to its address.

## Registration and the Agentverse profile

### How the agent gets onto Agentverse

`HackAgent` uses a **mailbox** by default, so it runs on your laptop but is reachable through Agentverse.
- **With `AGENTVERSE_API_KEY` set:** on startup it proves ownership of its address and publishes its profile. No clicks needed.
- **Without the key:** open the inspector link the agent logs and click **Connect → Mailbox**.
- **Agent at a public URL** (Render, Fly, a VM): call `fetch_hackkit.register.register_endpoint_agent(agent, "https://.../submit")`.

### Where each profile field comes from

| Profile field | Set it in code | Change it later via the Agentverse MCP |
|---|---|---|
| Name | `HackAgent(name=...)` | `update_user_agent_mailbox` (mailbox/local) / `update_user_agent` (hosted): `name` |
| **@handle** | `HackAgent(handle=...)` or `AGENT_HANDLE` in `.env` | **Not possible via MCP.** Change it in code and restart. |
| Short description | `HackAgent(description=...)` | same tools: `short_description` |
| README | `HackAgent(readme_path=...)` | same tools: `readme` |
| Avatar | `HackAgent(avatar_url=...)` | same tools: `avatar_url` |
| Protocols | automatic: chat, plus payment if `@agent.paid` is used | read-only |

Handle rules:
- 1–40 characters: letters, digits, `-`, `_` and `.`.
- Unique across all of Agentverse.
- Check availability first with `uv run hackkit handle <name>`. A taken handle fails registration with HTTP 409.

### Agentverse MCP (configured in `opencode.json`, `.mcp.json`, `.cursor/mcp.json`)

- **Lite server** (`https://mcp-lite.agentverse.ai/mcp`): enabled by default, with fewer tools, so it's friendlier to smaller models.
- **Full server** (`https://mcp.agentverse.ai/sse`): has every tool. Turn it on if a tool below is missing.
- **Auth:** an `Authorization: Bearer $AGENTVERSE_API_KEY` header. If a tool asks for `api_token`, pass the same key.

Useful workflows:
- **Inspect your agent:**
  - `get_user_agent_details` / `get_agent` with your address;
  - `agent_readiness_probe_mailbox` (mailbox) / `agent_readiness_probe` (hosted).
- **Edit your profile:** `update_user_agent_mailbox(address, name, short_description, readme)`.
- **Hosted agent** (runs on Agentverse, no laptop): `create_user_agent` → `update_user_agent_code` → `start_specific_user_agent` → `get_latest_logs_for_user_agent`. Hosted agents can't import `fetch-hackkit`; copy the pattern instead.
- **Discoverability:**
  - `search_agents` with the words a user would type, to see where you rank;
  - `start_agent_seo_eval` → `get_agent_seo_eval_results` to see how well ASI:One can match you.

### Getting discovered by ASI:One

ASI:One routes users by your **name, description, README and handle**:
- Write the README for routing: what the agent does, concrete example prompts, and the domains it covers.
- Keep the agent running (status `active`). A stopped mailbox agent isn't routed to.

## Submission checklist (Fetch.ai prize)

- [ ] Registered on Agentverse, status active, chat protocol published. `hackkit doctor` checks all of this.
- [ ] Works end-to-end inside ASI:One chat, with no custom frontend.
- [ ] Real tool use, MCP, or multi-agent orchestration, not just one LLM call.
- [ ] (Bonus) Interactive cards, the Payment Protocol, and error handling and recovery.
- [ ] Public GitHub repo README with **agent name + address** and both badges:
  `![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)`
  `![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)`
- [ ] A 3–5 minute demo video.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No seed phrase` | `uv run hackkit seed`, then put the phrase in `.env` |
| Agent not found in ASI:One | Is it running? Run `hackkit doctor`. Make the README specific, then try `@your-handle` directly. |
| `HTTP 409` on connect | Handle (or address) taken by another account. Pick a new handle. |
| `HTTP 401` on connect | Bad or expired `AGENTVERSE_API_KEY` |
| Card shows as plain text | The card is invalid. Look for `CardError` in the logs. |
| Button tap ignored | No `@agent.on_action` for that action, so it falls through to `on_text`. Check `msg.selection`. |
| Payment "not found" | The transaction is still indexing; the kit retries 3 times. On mainnet, check `FET_NETWORK`. |
| `There is no current event loop` (Python 3.14) | Use `HackAgent`, which creates the loop for you, or run on Python 3.13 |
