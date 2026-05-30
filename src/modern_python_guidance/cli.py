"""CLI entry point for modern-python-guidance."""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
from pathlib import Path

from modern_python_guidance import __version__
from modern_python_guidance.compat import VERSION_RE, version_compatible
from modern_python_guidance.guide_index import build_index
from modern_python_guidance.retrieve import retrieve
from modern_python_guidance.search import search as do_search
from modern_python_guidance.version_detect import detect_version


def main(argv: list[str] | None = None) -> None:
    with contextlib.suppress(AttributeError, OSError):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = argparse.ArgumentParser(
        prog="modern-python-guidance",
        description="Version-aware BAD/GOOD pattern guides for modern Python",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # search
    p_search = subparsers.add_parser("search", help="Search guides by keyword")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--python-version", help="Target Python version (e.g. 3.11)")
    p_search.add_argument("--category", help="Filter by category")
    p_search.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    p_search.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )

    # retrieve
    p_retrieve = subparsers.add_parser("retrieve", help="Retrieve guide(s) by ID")
    p_retrieve.add_argument("ids", help="Comma-separated guide IDs")
    p_retrieve.add_argument("--python-version", help="Target Python version")
    p_retrieve.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )

    # list
    p_list = subparsers.add_parser("list", help="List available guides")
    p_list.add_argument("--category", help="Filter by category")
    p_list.add_argument("--python-version", help="Filter by Python version")
    p_list.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )

    # detect-version
    p_detect = subparsers.add_parser("detect-version", help="Detect project Python version")
    p_detect.add_argument("--project-dir", type=Path, help="Project directory (default: cwd)")

    # mcp
    subparsers.add_parser("mcp", help="Start MCP server (JSON-RPC over stdio)")

    # setup
    p_setup = subparsers.add_parser(
        "setup",
        help="Register MCP server and link Agent Skills",
    )
    p_setup.add_argument("--mcp-only", action="store_true", help="MCP registration only")
    p_setup.add_argument("--skills-only", action="store_true", help="Skills symlink only")
    p_setup.add_argument(
        "--scope",
        choices=["user", "local"],
        default="user",
        help="MCP scope (default: user)",
    )
    p_setup.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for Skills symlink",
    )
    p_setup.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall",
        help="Reverse 'setup': deregister MCP server and unlink Agent Skills",
    )
    p_uninstall.add_argument("--mcp-only", action="store_true", help="MCP deregistration only")
    p_uninstall.add_argument("--skills-only", action="store_true", help="Skills unlink only")
    p_uninstall.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for Skills symlink",
    )
    p_uninstall.add_argument("--dry-run", action="store_true", help="Show what would be done")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(2)

    pv = getattr(args, "python_version", None)
    if pv is not None and not VERSION_RE.match(pv):
        parser.error(f"invalid --python-version format: {pv!r} (expected N.N, e.g. 3.11)")

    try:
        if args.command == "search":
            _cmd_search(args)
        elif args.command == "retrieve":
            _cmd_retrieve(args)
        elif args.command == "list":
            _cmd_list(args)
        elif args.command == "detect-version":
            _cmd_detect_version(args)
        elif args.command == "mcp":
            _cmd_mcp()
        elif args.command == "setup":
            _cmd_setup(args)
        elif args.command == "uninstall":
            _cmd_uninstall(args)
    except BrokenPipeError:
        sys.exit(0)


def _resolve_format(args: argparse.Namespace) -> str:
    if args.format is not None:
        return args.format
    return "human" if sys.stdout.isatty() else "json"


def _cmd_search(args: argparse.Namespace) -> None:
    index = build_index()
    results = do_search(
        index,
        args.query,
        python_version=args.python_version,
        category=args.category,
        limit=args.limit,
    )

    fmt = _resolve_format(args)

    if not results:
        if fmt == "human":
            print("No guides found.")
        else:
            print("[]")
        sys.exit(1)

    if fmt == "json":
        out = [
            {
                "id": r.guide_id,
                "title": r.meta.title,
                "category": r.meta.category,
                "layer": r.meta.layer,
                "tags": r.meta.tags,
                "python": r.meta.python,
                "frequency": r.meta.frequency,
                "score": r.score,
                "token_estimate": r.token_estimate,
                "fuzzy": r.fuzzy,
                "snippet": r.snippet,
            }
            for r in results
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for r in results:
            fuzzy_marker = " (fuzzy)" if r.fuzzy else ""
            print(f"  {r.guide_id:<40} score={r.score:<6.1f} [{r.meta.category}]{fuzzy_marker}")


def _cmd_retrieve(args: argparse.Namespace) -> None:
    index = build_index()
    guide_ids = [gid.strip() for gid in args.ids.split(",")]
    results = retrieve(index, guide_ids, python_version=args.python_version)

    fmt = _resolve_format(args)

    if not results:
        if fmt == "human":
            print("No guides found.")
        else:
            print("[]")
        sys.exit(1)

    if fmt == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            match_str = "YES" if r["version_match"] else "NO"
            print(f"--- {r['id']} (version match: {match_str}) ---")
            print(r["content"])
            print()


def _cmd_list(args: argparse.Namespace) -> None:
    index = build_index()
    metas = index.all_meta()

    if args.category:
        metas = [m for m in metas if m.category == args.category]

    if args.python_version:
        metas = [m for m in metas if version_compatible(m.python, args.python_version)]

    metas.sort(key=lambda m: (m.layer, m.category, m.id))

    fmt = _resolve_format(args)

    if not metas:
        if fmt == "human":
            print("No guides found.")
        else:
            print("[]")
        sys.exit(1)

    if fmt == "json":
        out = [
            {
                "id": m.id,
                "title": m.title,
                "category": m.category,
                "layer": m.layer,
                "python": m.python,
                "frequency": m.frequency,
            }
            for m in metas
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        current_cat = None
        for m in metas:
            if m.category != current_cat:
                current_cat = m.category
                print(f"\n[{current_cat}] (layer {m.layer})")
            print(f"  {m.id:<40} {m.title}")


def _cmd_detect_version(args: argparse.Namespace) -> None:
    version = detect_version(project_dir=args.project_dir)
    print(version)


def _cmd_mcp() -> None:
    from modern_python_guidance.mcp_server import serve

    serve()


def _cmd_setup(args: argparse.Namespace) -> None:
    from modern_python_guidance.setup_cmd import run_setup

    code = run_setup(
        scope=args.scope,
        mcp_only=args.mcp_only,
        skills_only=args.skills_only,
        project_dir=args.project_dir,
        dry_run=args.dry_run,
    )
    sys.exit(code)


def _cmd_uninstall(args: argparse.Namespace) -> None:
    from modern_python_guidance.uninstall_cmd import run_uninstall

    code = run_uninstall(
        mcp_only=args.mcp_only,
        skills_only=args.skills_only,
        project_dir=args.project_dir,
        dry_run=args.dry_run,
    )
    sys.exit(code)
