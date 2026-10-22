from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

import pytest
from fetch_hackkit import __version__, scaffold
from fetch_hackkit.cards import collect_actions, validate
from fetch_hackkit.cli import main


def _load_agent(path: Path):
    spec = importlib.util.spec_from_file_location("generated_agent", path / "agent.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generated_agent"] = module
    spec.loader.exec_module(module)
    return module


async def test_create_project_writes_a_runnable_project(tmp_path: Path, monkeypatch) -> None:
    project = scaffold.create_project(
        "Trip Planner", directory=tmp_path / "trip", check_handle=False
    )
    root = project.path
    expected = {
        "agent.py",
        "README.md",
        "pyproject.toml",
        ".python-version",
        ".env",
        ".env.example",
        ".gitignore",
        ".dockerignore",
        "Dockerfile",
        "AGENTS.md",
        "CLAUDE.md",
        "opencode.json",
        ".mcp.json",
        ".cursor/mcp.json",
        "tests/test_agent.py",
    }
    assert expected <= {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}

    for path in root.rglob("*"):
        if path.is_file():
            assert "__AGENT_" not in path.read_text() and "__PROJECT_" not in path.read_text(), path

    assert project.handle == "trip-planner"
    env = (root / ".env").read_text()
    assert "AGENT_HANDLE=trip-planner" in env
    seed = next(
        line.split("=", 1)[1] for line in env.splitlines() if line.startswith("AGENT_SEED_PHRASE=")
    )
    assert len(seed) >= 32
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
    assert project.address in (root / "README.md").read_text()
    assert f'"fetch-hackkit[mcp]>={__version__}"' in (root / "pyproject.toml").read_text()
    agents_md = (root / "AGENTS.md").read_text()
    assert "Trip Planner" in agents_md and "## Interactive cards (ASI:One UI)" in agents_md
    assert (root / "CLAUDE.md").resolve() == (root / "AGENTS.md").resolve()

    monkeypatch.setenv("AGENT_SEED_PHRASE", seed)
    monkeypatch.chdir(root)
    generated = _load_agent(root)
    menu = generated.menu()
    assert validate(menu.kind, menu.payload) == []
    assert collect_actions(menu.payload) <= set(generated.agent._action_handlers)
    assert generated.agent.address == project.address


def test_refuses_non_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        scaffold.create_project("A", directory=tmp_path, check_handle=False)


def test_taken_handle_gets_a_free_variant(monkeypatch) -> None:
    monkeypatch.setattr(scaffold, "resolve", lambda h: {"address": "x"} if h == "taken" else None)
    handle, note = scaffold._choose_handle("taken", check=True)
    assert handle.startswith("taken-") and "taken" in note
    assert scaffold._choose_handle("free", check=True) == ("free", "available")


def test_slugify() -> None:
    assert scaffold.slugify("Trip Planner 2.0!") == "trip-planner-2-0"
    assert scaffold.slugify("🙂") == "my-agent"


def test_cli_new(tmp_path: Path, capsys) -> None:
    assert main(["new", "Rent Splitter", "--dir", str(tmp_path / "rs"), "--no-check"]) == 0
    out = capsys.readouterr().out
    assert "@rent-splitter" in out and "uv run python agent.py" in out
    assert main(["new", "Rent Splitter", "--dir", str(tmp_path / "rs"), "--no-check"]) == 1
