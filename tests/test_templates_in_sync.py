"""`hackkit new` ships copies of this repo's AGENTS.md reference and coding-agent configs.
These tests fail if the copies drift from the originals."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "packages/fetch-hackkit/src/fetch_hackkit/templates"


def test_agents_reference_matches_repo_agents_md() -> None:
    repo = (ROOT / "AGENTS.md").read_text()
    shared = repo[repo.index("## Golden rules") :]
    assert (TEMPLATES / "agents_reference.md").read_text() == shared, (
        "AGENTS.md changed: copy everything from '## Golden rules' down into "
        "templates/agents_reference.md"
    )


def test_coding_agent_configs_match() -> None:
    pairs = {
        "opencode.json": "project/opencode.json.tmpl",
        ".mcp.json": "project/mcp.json.tmpl",
        ".cursor/mcp.json": "project/cursor_mcp.json.tmpl",
    }
    for repo_file, template in pairs.items():
        assert (ROOT / repo_file).read_text() == (TEMPLATES / template).read_text(), repo_file
