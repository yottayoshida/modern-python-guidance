"""CLI entry point for modern-python-guidance."""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
from pathlib import Path

from modern_python_guidance import __version__
from modern_python_guidance.check import CheckError, CheckMatch, check_file, sanitize_line
from modern_python_guidance.compat import VERSION_RE, version_compatible
from modern_python_guidance.guide_index import build_index
from modern_python_guidance.retrieve import retrieve, suggest_ids
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
        help="Register MCP server and link Agent Skills + Rules",
    )
    p_setup.add_argument("--mcp-only", action="store_true", help="MCP registration only")
    p_setup.add_argument(
        "--skills-only", action="store_true", help="Project-local artifacts only (Skills + Rules)"
    )
    p_setup.add_argument(
        "--scope",
        choices=["user", "local"],
        default="user",
        help="MCP scope (default: user)",
    )
    p_setup.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for Skills/Rules symlinks",
    )
    p_setup.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall",
        help="Reverse 'setup': deregister MCP server and unlink Agent Skills + Rules",
    )
    p_uninstall.add_argument("--mcp-only", action="store_true", help="MCP deregistration only")
    p_uninstall.add_argument(
        "--skills-only",
        action="store_true",
        help="Project-local artifacts only (Skills + Rules)",
    )
    p_uninstall.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for Skills/Rules symlinks",
    )
    p_uninstall.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # check
    p_check = subparsers.add_parser(
        "check",
        help="Scan a Python file for outdated patterns",
    )
    p_check.add_argument("file", type=Path, help="Python file to check")
    p_check.add_argument("--python-version", help="Target Python version (e.g. 3.11)")
    p_check.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )
    p_check.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always exit 0 even when patterns are found",
    )
    p_check.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output when no patterns are found (human format only)",
    )

    # hook
    p_hook = subparsers.add_parser(
        "hook",
        help="Claude Code hook subcommands",
    )
    hook_sub = p_hook.add_subparsers(dest="hook_name")
    hook_sub.add_parser(
        "claude-post-tool-use",
        help="PostToolUse hook: check .py files from stdin JSON",
    )

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
        elif args.command == "check":
            _cmd_check(args)
        elif args.command == "hook":
            _cmd_hook(args)
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
    guide_ids = [gid.strip() for gid in args.ids.split(",") if gid.strip()]
    if not guide_ids:
        print("No guide IDs provided.")
        sys.exit(1)
    results = retrieve(index, guide_ids, python_version=args.python_version)

    found_ids = {r["id"] for r in results}
    missing = [gid for gid in guide_ids if gid not in found_ids]

    fmt = _resolve_format(args)

    if fmt == "json":
        if missing:
            not_found = [{"id": gid, "suggestions": suggest_ids(index, gid)} for gid in missing]
            envelope = {"results": results, "not_found": not_found}
            print(json.dumps(envelope, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            match_str = "YES" if r["version_match"] else "NO"
            print(f"--- {r['id']} (version match: {match_str}) ---")
            print(r["content"])
            print()
        for gid in missing:
            suggestions = suggest_ids(index, gid)
            if suggestions:
                print(f"No guide found for '{gid}'. Did you mean:")
                for s in suggestions:
                    print(f"  {s}")
            else:
                print(f"No guide found for '{gid}'.")
                print("Run 'mpg list' to see available guides.")

    if missing:
        sys.exit(1)


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


def _cmd_check(args: argparse.Namespace) -> None:
    index = build_index()
    try:
        matches = check_file(args.file, index, python_version=args.python_version)
    except CheckError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    fmt = _resolve_format(args)

    if fmt == "json":
        _check_json(matches, args.file)
    elif not (args.quiet and not matches):
        _check_human(matches)

    if matches and not args.exit_zero:
        sys.exit(1)


def _check_json(matches: list[CheckMatch], file_path: Path) -> None:
    guide_ids = {m.guide_id for m in matches}
    out = {
        "file": str(file_path),
        "mpg_version": __version__,
        "matches": [
            {
                "line": m.line,
                "source_line": m.source_line,
                "guide_id": m.guide_id,
                "guide_title": m.guide_title,
                "category": m.category,
                "frequency": m.frequency,
                "snippet": m.snippet,
            }
            for m in matches
        ],
        "summary": {
            "total_matches": len(matches),
            "unique_guides": len(guide_ids),
            "guide_ids": sorted(guide_ids),
        },
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _check_human(matches: list[CheckMatch]) -> None:
    if not matches:
        print("No outdated patterns found.")
        return

    for m in matches:
        src = sanitize_line(m.source_line.strip())
        print(f"{m.guide_id:<40} line {m.line}: {src}")
        if m.snippet:
            snip = sanitize_line(m.snippet)
            print(f"{'':40}   {snip}")

    guide_ids = {m.guide_id for m in matches}
    unique = len(guide_ids)
    ids = ", ".join(sorted(guide_ids))
    ps = "" if len(matches) == 1 else "s"
    gs = "" if unique == 1 else "s"
    print(
        f"\n{len(matches)} outdated pattern{ps} found ({unique} guide{gs}). "
        f"Run `mpg retrieve {ids}` for details."
    )


def _cmd_hook(args: argparse.Namespace) -> None:
    if not args.hook_name:
        print("usage: modern-python-guidance hook <name>", file=sys.stderr)
        print("available hooks: claude-post-tool-use", file=sys.stderr)
        sys.exit(2)
    if args.hook_name == "claude-post-tool-use":
        _hook_post_tool_use()
    else:
        print(f"unknown hook: {args.hook_name}", file=sys.stderr)
        print("available hooks: claude-post-tool-use", file=sys.stderr)
        sys.exit(2)


def _hook_post_tool_use() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        file_path = data["tool_input"]["file_path"]
    except (KeyError, TypeError):
        sys.exit(0)

    if not isinstance(file_path, str) or not file_path.lower().endswith(".py"):
        sys.exit(0)

    path = Path(file_path)
    if not path.is_file():
        sys.exit(0)

    index = build_index()
    python_version = detect_version(project_dir=_project_dir_for_path(path))
    try:
        matches = check_file(path, index, python_version=python_version)
    except CheckError:
        sys.exit(0)

    if not matches:
        sys.exit(0)

    for m in matches:
        src = sanitize_line(m.source_line.strip())
        print(
            f"mpg: {m.guide_id} (line {m.line}): {src}",
            file=sys.stderr,
        )
    guide_ids = sorted({m.guide_id for m in matches})
    print(
        f"mpg: {len(matches)} outdated pattern(s). "
        f"Run `mpg retrieve {','.join(guide_ids)}` for modern alternatives.",
        file=sys.stderr,
    )
    sys.exit(2)


def _project_dir_for_path(path: Path) -> Path:
    current = path.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() or (candidate / ".python-version").is_file():
            return candidate
    return current
