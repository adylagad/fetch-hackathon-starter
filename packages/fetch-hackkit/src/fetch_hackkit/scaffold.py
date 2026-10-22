"""``hackkit new``: generate a minimal, ready-to-run agent project.

The project gets an agent with a menu card and an ASI:One tool, a README in
Agentverse profile shape, a fresh seed in ``.env``, tests, a Dockerfile, and
AGENTS.md plus opencode/Claude Code/Cursor configs for coding agents.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .register import HANDLE_MAX_LEN, resolve, validate_handle

# template file (under templates/project) -> path in the new project
FILES = {
    "agent.py.tmpl": "agent.py",
    "README.md.tmpl": "README.md",
    "pyproject.toml.tmpl": "pyproject.toml",
    "python-version.tmpl": ".python-version",
    "env.example.tmpl": ".env.example",
    "gitignore.tmpl": ".gitignore",
    "dockerignore.tmpl": ".dockerignore",
    "Dockerfile.tmpl": "Dockerfile",
    "tests/test_agent.py.tmpl": "tests/test_agent.py",
    "opencode.json.tmpl": "opencode.json",
    "mcp.json.tmpl": ".mcp.json",
    "cursor_mcp.json.tmpl": ".cursor/mcp.json",
}


@dataclass
class Project:
    path: Path
    name: str
    handle: str
    address: str
    handle_note: str = ""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "my-agent"


def _template(rel: str) -> str:
    return (files("fetch_hackkit") / "templates" / rel).read_text(encoding="utf-8")


def _choose_handle(wanted: str, check: bool) -> tuple[str, str]:
    """Return (handle, note). Picks a free variant if ``wanted`` is taken."""
    handle = validate_handle(wanted[:HANDLE_MAX_LEN].strip("-") or "my-agent")
    if not check:
        return handle, "not checked (--no-check)"
    try:
        if resolve(handle) is None:
            return handle, "available"
        for _ in range(5):
            candidate = validate_handle(f"{handle[: HANDLE_MAX_LEN - 5]}-{secrets.token_hex(2)}")
            if resolve(candidate) is None:
                return candidate, f"@{handle} was taken"
    except Exception as exc:  # offline etc.: keep the wanted handle
        return handle, f"could not check availability ({type(exc).__name__})"
    return handle, f"@{handle} is taken; pick another with `hackkit handle`"


def create_project(
    name: str,
    *,
    directory: Path | None = None,
    handle: str | None = None,
    check_handle: bool = True,
) -> Project:
    """Write a new agent project and return where it is and who it is."""
    from . import __version__
    from .doctor import identity_from_seed

    path = (directory or Path.cwd() / slugify(name)).resolve()
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"{path} already exists and is not empty")

    chosen, note = _choose_handle(
        handle.removeprefix("@") if handle else slugify(name), check_handle
    )
    seed = secrets.token_urlsafe(32)
    address, _wallet = identity_from_seed(seed)
    values = {
        "__AGENT_NAME__": name,
        "__AGENT_HANDLE__": chosen,
        "__AGENT_ADDRESS__": address,
        "__PROJECT_SLUG__": slugify(name),
        "__HACKKIT_VERSION__": __version__,
    }

    def render(text: str) -> str:
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    for src, dest in FILES.items():
        target = path / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(_template(f"project/{src}")), encoding="utf-8")

    agents_md = render(_template("project/AGENTS.md.tmpl")) + _template("agents_reference.md")
    (path / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    try:
        os.symlink("AGENTS.md", path / "CLAUDE.md")
    except OSError:  # e.g. Windows without symlink rights
        (path / "CLAUDE.md").write_text(agents_md, encoding="utf-8")

    env = render(_template("project/env.example.tmpl")).replace(
        "AGENT_SEED_PHRASE=\n", f"AGENT_SEED_PHRASE={seed}\n", 1
    )
    env_path = path / ".env"
    env_path.write_text(env, encoding="utf-8")
    env_path.chmod(0o600)
    return Project(path=path, name=name, handle=chosen, address=address, handle_note=note)
