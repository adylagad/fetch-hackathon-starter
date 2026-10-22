"""MCP: give ASI:One the tools of a remote MCP server (DeepWiki answers questions about
any public GitHub repo). Swap the URL for any MCP server: Agentverse, GitHub, your own.
"""

from __future__ import annotations

from fetch_hackkit import ASI1, ASI1Error, HackAgent, cards
from fetch_hackkit.mcp import call_mcp_tool, mcp_tools

DEEPWIKI = "https://mcp.deepwiki.com/mcp"


def mcp_form() -> cards.Card:
    return cards.form(
        "Ask a GitHub repo",
        [
            cards.field(
                "repo", "Repository (owner/name)", required=True, placeholder="fetchai/uAgents"
            ),
            cards.field(
                "question",
                "Question",
                required=True,
                placeholder="How does the mailbox client deliver messages?",
            ),
        ],
        submit=cards.cta("Ask via MCP", "mcp_ask", primary=True),
        narration="I'll connect to the **DeepWiki MCP server** and let ASI:One use its tools to answer.",
    )


def register(agent: HackAgent) -> None:
    @agent.on_action("mcp_form")
    async def show_form(ctx, msg, sel):
        return mcp_form()

    @agent.on_action("mcp_ask")
    async def ask(ctx, msg, sel):
        repo = str(sel.get("repo") or "fetchai/uAgents")
        question = str(sel.get("question") or msg.text)
        try:
            llm = ASI1()
        except ASI1Error:  # no LLM: call the MCP tool directly
            answer = await call_mcp_tool(
                DEEPWIKI, "ask_wiki_question", {"repoName": repo, "question": question}
            )
            return f"**{repo}** (direct MCP call):\n\n{answer}"
        tools = await mcp_tools(DEEPWIKI, include={"ask_wiki_question", "read_wiki_structure"})
        answer = await llm.run_tools(
            f"Repository: {repo}\nQuestion: {question}\nAnswer briefly, citing files where useful.",
            tools=tools,
            on_call=lambda name, args, _r: ctx.logger.info(f"MCP tool {name}({args})"),
        )
        return f"**{repo}** (ASI:One + MCP tools):\n\n{answer}"
