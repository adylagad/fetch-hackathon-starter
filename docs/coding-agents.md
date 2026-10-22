# Coding with ASI:One (opencode, Claude Code, Cursor, and others)

Every hacker gets ASI:One credits. Point your coding agent at ASI:One and it writes your agent code. This repo is pre-configured: `AGENTS.md` explains the codebase to the coding agent, and the Agentverse MCP lets it inspect and update your agent on Agentverse.

## opencode + ASI:One (recommended)

[opencode](https://opencode.ai) is an open-source terminal coding agent that can use any OpenAI-compatible model, including ASI:One.

1. **Install opencode.** See https://opencode.ai for the current install command, e.g. `npm i -g opencode-ai`.
2. **Export your keys** in the shell you'll run opencode from:
   ```bash
   export ASI_ONE_API_KEY=...        # https://asi1.ai/developer
   export AGENTVERSE_API_KEY=...     # https://agentverse.ai/profile/api-keys
   ```
3. **Start opencode** from the repo root: `opencode`. It reads `opencode.json` (ASI:One provider + Agentverse MCP) and `AGENTS.md` automatically.
4. **Pick a model:** `/models` → **ASI:One / ASI1**. Use `asi1-ultra` for hard multi-file changes and `asi1-mini` for quick edits.
5. **Try prompts like these:**
   - *Add a form card to agent/flows that collects a city and date, then a review card, then calls a weather API tool.*
   - *Use the agentverse MCP to show my agent's profile, then improve its README for ASI:One routing.*
   - *Run the tests and fix anything that fails.*

`opencode.json` enables the full Agentverse MCP server (`https://mcp.agentverse.ai/mcp`). A smaller **lite** server is included but disabled (`agentverse-lite`); it wasn't responding when this was tested. Flip `"enabled"` if it's back up and you want fewer tools in the model's context.

## Claude Code and Cursor

Both read `AGENTS.md`/`CLAUDE.md` and pick up the Agentverse MCP from `.mcp.json` (Claude Code) or `.cursor/mcp.json` (Cursor), using `AGENTVERSE_API_KEY` from your environment.

You **can't** run Claude Code or Cursor's agent *on* ASI:One models. Claude Code speaks the Anthropic API, and ASI:One is OpenAI-compatible. These tools still get the full repo context and the Agentverse tools.

## Other OpenAI-compatible tools

Any tool with a "custom OpenAI-compatible provider" setting can use ASI:One. Examples: Cline, Continue, Roo Code, aider, Zed.
- Base URL: `https://api.asi1.ai/v1`
- API key: your ASI:One key
- Model: `asi1` (or `asi1-ultra` / `asi1-mini`)

Example for aider:
```bash
export OPENAI_API_BASE=https://api.asi1.ai/v1
export OPENAI_API_KEY=$ASI_ONE_API_KEY
aider --model openai/asi1
```

## Tips for good results

- **Name the file and the pattern:** "add a flow in `agent/flows/` like `mcp_demo.py`" works better than "add a feature".
- **Ask it to run** `uv run pytest -q` and `uv run hackkit doctor` before you demo.
- **Keep secrets out of prompts.** The agent reads them from `.env`.
