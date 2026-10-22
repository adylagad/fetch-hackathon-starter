"""``hackkit`` command line: new, seed, whoami, handle, doctor."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _seed(_: argparse.Namespace) -> int:
    from .doctor import identity_from_seed

    seed = secrets.token_urlsafe(32)
    address, wallet = identity_from_seed(seed)
    print(f"AGENT_SEED_PHRASE={seed}\n")
    print(f"# agent address: {address}\n# FET wallet:    {wallet}")
    print("\nPut the first line in .env. Never commit it: the seed *is* your agent.")
    return 0


def _whoami(_: argparse.Namespace) -> int:
    from .doctor import identity_from_seed

    seed = os.getenv("AGENT_SEED_PHRASE")
    if not seed:
        print("AGENT_SEED_PHRASE is not set (try `hackkit seed`)", file=sys.stderr)
        return 1
    address, wallet = identity_from_seed(seed)
    print(f"agent address: {address}\nFET wallet:    {wallet}")
    print(f"profile:       https://agentverse.ai/agents/details/{address}/profile")
    return 0


def _handle(args: argparse.Namespace) -> int:
    from .register import resolve, validate_handle

    try:
        handle = validate_handle(args.handle)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1
    record = resolve(handle)
    if record is None:
        print(f"✅ @{handle} is available")
        return 0
    print(f"❌ @{handle} is taken by {record.get('address')}")
    return 1


def _new(args: argparse.Namespace) -> int:
    from .scaffold import create_project

    try:
        project = create_project(
            args.name,
            directory=Path(args.dir) if args.dir else None,
            handle=args.handle,
            check_handle=not args.no_check,
        )
    except (FileExistsError, ValueError) as exc:
        print(f"❌ {exc}")
        return 1
    try:
        where = project.path.relative_to(Path.cwd())
    except ValueError:
        where = project.path
    print(f"✅ Created {project.name} in {where}/")
    print(f"   handle:  @{project.handle} ({project.handle_note})")
    print(f"   address: {project.address}")
    print("   identity: a fresh seed is in .env (never commit it)\n")
    print("Next:")
    print(f"  cd {where}")
    print("  # add ASI_ONE_API_KEY and AGENTVERSE_API_KEY to .env")
    print("  uv sync")
    print("  uv run python agent.py")
    print(f"  # then on https://asi1.ai say: @{project.handle} hi")
    print("\nCoding agent: run `opencode` here (ASI:One + Agentverse MCP), or Claude Code/Cursor.")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import run

    handle = args.handle or os.getenv("AGENT_HANDLE")
    checks = run(readme=Path(args.readme), handle=handle)
    for c in checks:
        print(f"{c.icon} {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            print(f"      fix: {c.fix}")
    failed = sum(c.status == "fail" for c in checks)
    print(f"\n{'All good. Ship it!' if not failed else f'{failed} check(s) failed.'}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(find_dotenv(usecwd=True))
    parser = argparse.ArgumentParser(prog="hackkit", description="Fetch.ai hackathon helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="create a ready-to-run agent project")
    p.add_argument("name", help='agent name, e.g. "Trip Planner"')
    p.add_argument("--dir", help="where to create it (default: ./<name-slug>)")
    p.add_argument("--handle", help="Agentverse @handle (default: from the name)")
    p.add_argument("--no-check", action="store_true", help="don't check handle availability")
    p.set_defaults(fn=_new)
    sub.add_parser("seed", help="generate a secure seed phrase + show its address").set_defaults(
        fn=_seed
    )
    sub.add_parser(
        "whoami", help="show the agent address + wallet for AGENT_SEED_PHRASE"
    ).set_defaults(fn=_whoami)
    p = sub.add_parser("handle", help="check if an Agentverse @handle is free")
    p.add_argument("handle")
    p.set_defaults(fn=_handle)
    p = sub.add_parser("doctor", help="check your agent against the submission requirements")
    p.add_argument("--readme", default="README.md", help="README to check (default README.md)")
    p.add_argument("--handle", help="expected @handle (default $AGENT_HANDLE)")
    p.set_defaults(fn=_doctor)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
