![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Fetch.ai Hackathon Starter

Everything you need to build a Fetch.ai agent that works inside ASI:One. It has:

- **`fetch-hackkit`**, a small Python library. It covers:
  - the Agent Chat Protocol;
  - **ASI:One interactive cards**;
  - **ASI:One LLM with tool calling**;
  - **FET payments**;
  - **MCP tools**;
  - **agent-to-agent** calls;
  - **Agentverse registration**, including your `@handle`.
- **Hackkit Guide**, a showcase agent built on it. Clone it and turn it into your project.
- **AI coding setup**: `AGENTS.md` plus ready-made configs, so opencode (running on your ASI:One credits), Claude Code or Cursor can write correct Fetch.ai code from the first prompt.

> Status: early. Built for Cal Hacks 13.0. Not an official Fetch.ai project (yet).

## Quick start (5 minutes)

You need [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
git clone https://github.com/adylagad/fetch-hackathon-starter
cd fetch-hackathon-starter
uv sync --all-packages

cd agent
cp .env.example .env
uv run hackkit seed            # paste the AGENT_SEED_PHRASE line into .env
uv run hackkit handle my-team-agent   # pick a free @handle, put it in AGENT_HANDLE
# add ASI_ONE_API_KEY (asi1.ai/developer) and AGENTVERSE_API_KEY (agentverse.ai/profile/api-keys)

uv run python agent.py
```

With `AGENTVERSE_API_KEY` set, the agent connects itself to Agentverse and publishes its profile. Open [asi1.ai](https://asi1.ai), say `@my-team-agent hi`, and tap through the demo.

## What the showcase agent demonstrates

| Say or tap | Feature | Code |
|---|---|---|
| "hi" | Carousel menu card | `agent/flows/menu.py` |
| Interactive cards | Every card kind, plus form → review → confirm | `agent/flows/gallery.py` |
| Ask anything | ASI:One calling tools (Agentverse search, docs) | `agent/flows/ask.py` |
| Paid project brief | Payment Protocol, 0.1 testnet FET verified on-chain | `agent/flows/paid_brief.py` |
| MCP tools | ASI:One + the DeepWiki MCP server | `agent/flows/mcp_demo.py` |
| Agent-to-agent | Delegating to another agent over the chat protocol | `agent/flows/peer_demo.py` |

## The library in 20 lines

```python
from fetch_hackkit import ASI1, HackAgent, cards

agent = HackAgent(name="Trip Planner", handle="trip-planner",
                  description="Plans weekend trips", readme_path="README.md")

def get_weather(city: str) -> str:
    """Current weather for a city."""
    return "18C and sunny"

@agent.on_text
async def on_text(ctx, msg):
    return cards.carousel("Pick a city", [
        cards.item("sf", "San Francisco", action="plan"),
        cards.item("la", "Los Angeles", action="plan"),
    ], narration="Where to?")

@agent.on_action("plan")
async def plan(ctx, msg, sel):
    return await ASI1().run_tools(f"Plan a weekend in {sel['id']}", tools=[get_weather])

agent.run()
```

The full reference is [AGENTS.md](AGENTS.md). It's written for AI coding agents and is just as useful for you.

## Build with an AI coding agent on ASI:One

```bash
export ASI_ONE_API_KEY=... AGENTVERSE_API_KEY=...
opencode            # uses opencode.json: ASI:One models + the Agentverse MCP
```

See [docs/coding-agents.md](docs/coding-agents.md) for opencode, Claude Code, Cursor, Cline, aider and others.

## Before you submit

```bash
cd agent && uv run hackkit doctor --readme ../README.md
```

`hackkit doctor` checks:
- your seed and keys;
- that the agent is on your Agentverse account and active on the Almanac;
- that the chat protocol is published;
- that your `@handle` points to this agent;
- that the README has the badges and your agent's address.

## Repo layout

```
packages/fetch-hackkit/   the library (published to PyPI as fetch-hackkit)
agent/                    the showcase agent: start here
AGENTS.md                 reference for humans and coding agents (CLAUDE.md links here)
opencode.json             opencode: ASI:One provider + Agentverse MCP
.mcp.json, .cursor/       Agentverse MCP for Claude Code / Cursor
docs/coding-agents.md     coding agents on ASI:One
```

## Development

```bash
uv run pytest -q && uv run ruff check . && uv run mypy
```

MIT licensed.
