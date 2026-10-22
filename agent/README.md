![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![tag:chatprotocol](https://img.shields.io/badge/chatprotocol-1D3BD4)

# Hackkit Guide

An interactive tour of building agents on Fetch.ai, run entirely inside ASI:One chat. It shows interactive cards, ASI:One tool calling, FET payments through the Payment Protocol, MCP tools, and agent-to-agent delegation, and it answers questions about building agents.

**Agent address:** `agent1...`. Replace this with the output of `uv run hackkit whoami`.

## What it can do

- **Interactive cards gallery:** live examples of carousel, detail, form, review and custom cards. Each one shows the exact selection your agent receives.
- **Q&A with tools:** ASI:One calls real tools. It searches Agentverse for live agents and links the right documentation page.
- **Paid project brief:** pay 0.1 testnet FET and get a structured hackathon project brief. The payment is verified on-chain before any work is done.
- **MCP tools:** ask questions about any public GitHub repository through the DeepWiki MCP server.
- **Agent-to-agent:** forwards your question to another agent over the chat protocol and relays its answer.

## Example prompts

- Hi
- Show me the interactive cards gallery
- Find agents on Agentverse that can book flights
- Where are the docs for the payment protocol?
- How does the uAgents mailbox deliver messages?
- Write me a project brief for an agent that splits rent between roommates

## Built with

[fetch-hackkit](https://github.com/adylagad/fetch-hackathon-starter), uAgents, the Agent Chat Protocol, the Agent Payment Protocol, ASI:One, and MCP.
