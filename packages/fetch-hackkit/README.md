# fetch-hackkit

Batteries for [Fetch.ai](https://fetch.ai) hackathon agents. Build a uAgent that works inside ASI:One in a few lines:

- **Chat protocol** done for you: acknowledgements, sessions, `@mention` stripping, friendly error replies.
- **ASI:One interactive cards**: typed builders for carousel, detail, form, review and custom cards, plus validation and tap parsing (JSON *and* planner prose).
- **ASI:One LLM**: `ask`, `structured` (Pydantic) and `run_tools`, which turns plain Python functions into tools.
- **Payments**: `@agent.paid(...)` puts any action behind the Agent Payment Protocol with on-chain FET verification.
- **MCP**: use any remote MCP server's tools from your agent.
- **Multi-agent**: `ask_agent(ctx, "@handle", "question")`.
- **Agentverse**: mailbox auto-connect with name, `@handle`, description and README, plus the `hackkit doctor` pre-submission checks.

```bash
pip install fetch-hackkit          # or: pip install "fetch-hackkit[mcp]"
```

```python
from fetch_hackkit import HackAgent, cards

agent = HackAgent(name="Trip Planner", handle="trip-planner", readme_path="README.md")

@agent.on_text
async def on_text(ctx, msg):
    return cards.carousel("Pick a city", [cards.item("sf", "San Francisco", action="plan")])

@agent.on_action("plan")
async def plan(ctx, msg, sel):
    return f"Planning {sel['id']}..."

agent.run()
```

Environment (`.env` is loaded automatically):
- `AGENT_SEED_PHRASE` (required; generate with `hackkit seed`)
- `ASI_ONE_API_KEY`
- `AGENTVERSE_API_KEY`
- `AGENT_HANDLE`

## CLI

```
hackkit seed            generate a secure seed phrase (+ its address and wallet)
hackkit whoami          address, wallet and Agentverse profile URL for your seed
hackkit handle NAME     is @NAME free on Agentverse?
hackkit doctor          check the agent against hackathon submission requirements
```

The starter repo, full docs and showcase agent are at https://github.com/adylagad/fetch-hackathon-starter. Requires Python 3.11+, `uagents` 0.26+ and `uagents-core` 0.4.12+. MIT licensed.
