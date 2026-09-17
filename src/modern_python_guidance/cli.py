"""CLI entry point for modern-python-guidance."""

from __future__ import annotations

import argparse
import codecs
import contextlib
import errno
import json
import logging
import os
import signal
import stat
import sys
import unicodedata
from pathlib import Path
from typing import NoReturn

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from modern_python_guidance import __version__
from modern_python_guidance.check import CheckError, CheckMatch, check_file, sanitize_line
from modern_python_guidance.compat import VERSION_RE, version_compatible
from modern_python_guidance.dependency_compat import DependencyContext, assess_dependencies
from modern_python_guidance.detection_coverage import (
    DetectionCoverage,
    detection_coverage,
    detection_metadata,
)
from modern_python_guidance.doctor import diagnose_all, summarize
from modern_python_guidance.frontmatter import VALID_FREQUENCIES, VALID_LAYERS
from modern_python_guidance.guide_index import build_index, meta_selected
from modern_python_guidance.project_dependencies import find_dependency_context
from modern_python_guidance.retrieve import retrieve, suggest_ids
from modern_python_guidance.search import search as do_search
from modern_python_guidance.version_detect import (
    DEFAULT_VERSION,
    PythonVersionResolution,
    resolve_python_version,
)

# The single source for which commands exist: `build_parser` registers exactly
# these and `_epilog` renders exactly these, so a command cannot be in one and
# not the other. argparse has no notion of grouped subcommands, hence composing
# the listing here and leaving the automatic one empty by withholding `help=`
# from each add_parser call — passing argparse.SUPPRESS prints "==SUPPRESS==".
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Guidance",
        (
            ("search", "Search guides by keyword"),
            ("retrieve", "Retrieve guide(s) by ID"),
            ("list", "List available guides"),
            ("check", "Scan a Python file for outdated patterns"),
            ("detect-version", "Detect project Python version"),
        ),
    ),
    (
        "Integration",
        (
            ("setup", "Register MCP server and link Agent Skills + Rules"),
            ("uninstall", "Reverse 'setup'"),
            ("doctor", "Report the state of every delivery channel"),
            ("mcp", "Start MCP server (JSON-RPC over stdio)"),
            ("hook", "Claude Code hook subcommands"),
        ),
    ),
)

EXAMPLES: tuple[tuple[str, str], ...] = (
    ('mpg search "typing list"', "find guides by keyword"),
    ("mpg retrieve use-builtin-generics", "print one guide in full"),
    ("mpg list --layer 2 --frequency high", "browse a slice of the catalog"),
    ("mpg check app.py", "scan a file for outdated patterns"),
)


def _epilog() -> str:
    lines = ["commands:"]
    for title, entries in COMMAND_GROUPS:
        lines.append(f"  {title}")
        lines.extend(f"    {name:<16}{description}" for name, description in entries)
        lines.append("")
    lines.append("examples:")
    for command, note in EXAMPLES:
        # The note goes on its own line so that a line starting with `mpg ` is
        # always a complete command — the help text stays the single source for
        # what these examples are, and checking them needs no parsing rules.
        lines.append(f"  # {note}")
        lines.append(f"  {command}")
    lines.append("")
    lines.append("Run `mpg <command> --help` for the options a command takes.")
    return "\n".join(lines)


def _limit_type(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be an integer, got '{value}'") from None
    if n < 1 or n > 50:
        raise argparse.ArgumentTypeError(f"must be between 1 and 50, got {n}")
    return n


def _dependency_version_type(value: str) -> tuple[str, str, str]:
    """Parse a CLI override without consulting the target environment."""
    try:
        key, raw_version = value.split("=", 1)
        kind, raw_name = key.split(":", 1)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "must be KIND:NAME=VERSION (for example package:pydantic=2.10.0)"
        ) from None
    name = canonicalize_name(raw_name)
    if kind not in {"package", "tool"} or not name or not raw_version:
        raise argparse.ArgumentTypeError(
            "kind must be package or tool and name/version must be non-empty"
        )
    try:
        version = str(Version(raw_version))
    except InvalidVersion:
        raise argparse.ArgumentTypeError(f"invalid dependency version: {raw_version!r}") from None
    return kind, name, version


def _dependency_overrides(
    values: list[tuple[str, str, str]] | None, parser: argparse.ArgumentParser
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for kind, name, version in values or []:
        key = f"{kind}:{name}"
        if key in overrides:
            parser.error(f"duplicate --dependency-version for {key}")
        overrides[key] = version
    return overrides


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """Catalog selection flags shared by search and list.

    ``--layer`` needs an explicit int type: argparse hands over strings by
    default, and comparing a string against the parsed int layer excludes every
    guide silently — an empty result with no error, and a CLI that disagrees
    with the MCP tools, which receive a real JSON integer.
    """
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument(
        "--layer",
        type=int,
        choices=sorted(VALID_LAYERS),
        help="Filter by layer: 1 stdlib, 2 frameworks, 3 toolchain",
    )
    parser.add_argument(
        "--frequency",
        choices=sorted(VALID_FREQUENCIES),
        help="Filter by how often the pattern is gotten wrong",
    )


def _add_dependency_arguments(
    parser: argparse.ArgumentParser, *, include_incompatible: bool = False
) -> None:
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory used to read dependency evidence (default: current directory)",
    )
    parser.add_argument(
        "--dependency-version",
        action="append",
        type=_dependency_version_type,
        dest="dependency_versions",
        metavar="KIND:NAME=VERSION",
        help="Exact dependency override; repeatable",
    )
    if include_incompatible:
        parser.add_argument(
            "--include-incompatible",
            action="store_true",
            help="Include guidance proven incompatible with project dependencies",
        )


def build_parser() -> argparse.ArgumentParser:
    """Assemble the CLI parser, separately from running it.

    Kept apart from ``main`` so the help text and the commands it advertises can
    be inspected without executing anything: a subprocess cannot tell a parse
    error from a command that parsed and then failed, since both exit 2.
    """
    parser = argparse.ArgumentParser(
        prog="modern-python-guidance",
        description="Version-aware BAD/GOOD pattern guides for modern Python",
        epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        help="one of the commands listed below",
    )

    # Registered from the same table the listing is rendered from, so a command
    # cannot exist in one and not the other. Each block below then claims its
    # parser by name and adds the arguments it takes.
    registered = {
        name: subparsers.add_parser(name)
        for _title, entries in COMMAND_GROUPS
        for name, _description in entries
    }

    # search
    p_search = registered["search"]
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--python-version", help="Target Python version (e.g. 3.11)")
    _add_selection_arguments(p_search)
    p_search.add_argument(
        "--limit", type=_limit_type, default=10, help="Max results, 1-50 (default: 10)"
    )
    _add_dependency_arguments(p_search, include_incompatible=True)
    p_search.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )

    # retrieve
    p_retrieve = registered["retrieve"]
    p_retrieve.add_argument("ids", help="Comma-separated guide IDs")
    p_retrieve.add_argument("--python-version", help="Target Python version")
    p_retrieve.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )
    _add_dependency_arguments(p_retrieve)

    # list
    p_list = registered["list"]
    _add_selection_arguments(p_list)
    p_list.add_argument("--python-version", help="Filter by Python version")
    p_list.add_argument(
        "--with-content",
        action="store_true",
        help="Include each guide's full body in the output",
    )
    p_list.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )
    _add_dependency_arguments(p_list, include_incompatible=True)

    # detect-version
    p_detect = registered["detect-version"]
    p_detect.add_argument("--project-dir", type=Path, help="Project directory (default: cwd)")
    p_detect.add_argument(
        "--format",
        choices=["json", "plain"],
        default="plain",
        help="Output format (default: plain)",
    )

    # mcp takes no arguments of its own.

    # setup
    p_setup = registered["setup"]
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
        help="Target project for local MCP and project artifacts",
    )
    p_setup.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_setup.add_argument(
        "--no-hook",
        action="store_true",
        help="Do not register the PostToolUse hook (removes it if already present)",
    )
    p_setup.add_argument(
        "--with-hook",
        action="store_true",
        help="Register the PostToolUse hook even if this project already has mpg artifacts",
    )

    # uninstall
    p_uninstall = registered["uninstall"]
    p_uninstall.add_argument("--mcp-only", action="store_true", help="MCP deregistration only")
    p_uninstall.add_argument(
        "--skills-only",
        action="store_true",
        help="Project-local artifacts only (Skills + Rules)",
    )
    p_uninstall.add_argument(
        "--project-dir",
        type=Path,
        help="Target project for local MCP and project artifacts",
    )
    p_uninstall.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # doctor
    p_doctor = registered["doctor"]
    p_doctor.add_argument(
        "--project-dir",
        type=Path,
        help="Project whose Skills/Rules/hook to inspect (default: nearest project root)",
    )
    p_doctor.add_argument(
        "--run-interpreter",
        action="store_true",
        help=(
            "Run the hook's registered interpreter to check mpg loads in it."
            " Off by default: the command comes from a settings file, which may"
            " have arrived with a cloned repository"
        ),
    )

    # check
    p_check = registered["check"]
    p_check.add_argument("file", type=Path, help="Python file to check")
    p_check.add_argument("--python-version", help="Target Python version (e.g. 3.11)")
    p_check.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        help="Output format (default: json when piped, human when TTY)",
    )
    _add_dependency_arguments(p_check)
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
    p_hook = registered["hook"]
    hook_sub = p_hook.add_subparsers(dest="hook_name")
    hook_sub.add_parser(
        "claude-post-tool-use",
        help="PostToolUse hook: check .py files from stdin JSON",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    with contextlib.suppress(AttributeError, OSError):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = build_parser()
    args = parser.parse_args(argv)

    if hasattr(args, "dependency_versions"):
        args.dependency_overrides = _dependency_overrides(args.dependency_versions, parser)

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
        elif args.command == "doctor":
            _cmd_doctor(args)
        elif args.command == "check":
            _cmd_check(args)
        elif args.command == "hook":
            _cmd_hook(args)
        else:
            # Reachable only by listing a command in COMMAND_GROUPS without
            # wiring it here: the parser accepts it, so it would otherwise exit
            # 0 having silently done nothing.
            parser.error(f"command is not implemented: {args.command}")
    except BrokenPipeError:
        sys.exit(0)


def _resolve_format(args: argparse.Namespace) -> str:
    if args.format is not None:
        return args.format
    return "human" if sys.stdout.isatty() else "json"


def _cmd_search(args: argparse.Namespace) -> None:
    index = build_index()
    resolution = _python_resolution(args)
    context = _dependency_context(args)
    results = do_search(
        index,
        args.query,
        python_version=resolution.version,
        category=args.category,
        layer=args.layer,
        frequency=args.frequency,
        limit=args.limit,
        dependency_context=context,
        include_incompatible=args.include_incompatible,
    )

    fmt = _resolve_format(args)

    if not results:
        if fmt == "human":
            print(_target_python_heading(resolution))
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
                "target_python": resolution.as_dict(),
                "snippet": r.snippet,
                **detection_metadata(index.get(r.guide_id)),
                **_dependency_json(
                    r.meta.applies_to_packages, r.meta.applies_to_tools, r.dependency_assessment
                ),
            }
            for r in results
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(_target_python_heading(resolution))
        for r in results:
            fuzzy_marker = " (fuzzy)" if r.fuzzy else ""
            assessment = r.dependency_assessment
            suffix = _human_dependency_suffix(assessment.status, assessment.reasons)
            print(
                f"  {r.guide_id:<40} score={r.score:<6.1f} [{r.meta.category}]"
                f"{fuzzy_marker}{suffix}"
            )


def _cmd_retrieve(args: argparse.Namespace) -> None:
    index = build_index()
    resolution = _python_resolution(args)
    guide_ids = [gid.strip() for gid in args.ids.split(",") if gid.strip()]
    if not guide_ids:
        print("No guide IDs provided.")
        sys.exit(1)
    results = retrieve(
        index,
        guide_ids,
        python_version=resolution.version,
        dependency_context=_dependency_context(args),
    )
    for result in results:
        result["target_python"] = resolution.as_dict()

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
        print(_target_python_heading(resolution))
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
    resolution = _python_resolution(args)
    metas = index.all_meta()

    metas = [
        m
        for m in metas
        if meta_selected(m, category=args.category, layer=args.layer, frequency=args.frequency)
    ]

    metas = [m for m in metas if version_compatible(m.python, resolution.version)]

    context = _dependency_context(args)
    assessed = [
        (m, _assess_meta(m.applies_to_packages, m.applies_to_tools, context)) for m in metas
    ]
    if not args.include_incompatible:
        assessed = [
            (m, assessment) for m, assessment in assessed if assessment.status != "incompatible"
        ]
    assessed.sort(key=lambda item: (item[0].layer, item[0].category, item[0].id))

    fmt = _resolve_format(args)

    if not assessed:
        if fmt == "human":
            print(_target_python_heading(resolution))
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
                "target_python": resolution.as_dict(),
                **detection_metadata(index.get(m.id)),
                **_dependency_json(m.applies_to_packages, m.applies_to_tools, assessment),
                **({"content": index.get(m.id).body} if args.with_content else {}),
            }
            for m, assessment in assessed
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(_target_python_heading(resolution))
        current_cat = None
        for m, assessment in assessed:
            if m.category != current_cat:
                current_cat = m.category
                print(f"\n[{current_cat}] (layer {m.layer})")
            suffix = _human_dependency_suffix(assessment.status, assessment.reasons)
            print(f"  {m.id:<40} {m.title}{suffix}")
            if args.with_content:
                print()
                print(index.get(m.id).body)
                print()


def _cmd_detect_version(args: argparse.Namespace) -> None:
    resolution = _python_resolution(args)
    if args.format == "json":
        print(json.dumps({"python_version": resolution.version, "source": resolution.source}))
    else:
        print(resolution.version)


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
        no_hook=args.no_hook,
        with_hook=args.with_hook,
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


_SHOWN_ESCAPED = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})
"""Unicode categories `_printable` renders as escapes: controls, format
characters (bidirectional overrides, zero-width, tags), line and paragraph
separators, and surrogates."""


def _printable(text: str) -> str:
    """`text` with every character that could act on a terminal shown instead.

    What `doctor` prints comes from a settings file, a link's destination, and
    `claude mcp get` — all of which a cloned repository can supply. A newline
    in a registered `command` wrote a whole fabricated `mcp  present` line into
    the report (#245); an escape sequence can erase and redraw one on a
    terminal; a lone surrogate from JSON's `\\ud800` made `print` itself raise.
    Escaping at the one place output is written covers every interpolation,
    including the ones nobody has added yet.

    Escaped, not deleted, so the reader can see something was there.
    `surrogateescape` carries an undecodable byte as U+DC80-DCFF, and that is
    shown as the byte it was (`\\xff`) — a raw 0x9B is CSI on an 8-bit
    terminal and passed straight through before. A backslash is left alone:
    a literal `\\x0a` in a path now reads like an escaped newline, which is
    ambiguous to a reader but cannot add a line.
    """
    if text.isprintable():
        return text
    return "".join(_shown(char) for char in text)


def _shown(char: str) -> str:
    if unicodedata.category(char) not in _SHOWN_ESCAPED:
        return char
    code = ord(char)
    if 0xDC80 <= code <= 0xDCFF:
        return f"\\x{code - 0xDC00:02x}"
    if code <= 0xFF:
        return f"\\x{code:02x}"
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


@contextlib.contextmanager
def _confined_doctor_output():
    """While `doctor` writes, stdout and stderr cannot emit a byte a terminal obeys.

    Escaping by Unicode category is not enough on its own, because the
    terminal sees encoded bytes: under cp1251, U+2026 is written as 0x85 (NEL)
    and U+203A as 0x9B (CSI) — both printable characters, so `_printable` leaves
    them, and both control characters by the time they are bytes. A stream
    that is not UTF-8 is switched to ASCII with backslash escapes; a UTF-8
    one only stops raising on a character it cannot encode. A stream without
    `reconfigure` (a replaced `sys.stdout`) is left as it is.

    Restored on the way out, `SystemExit` included: these are the process's
    own streams, and a caller running `main(["doctor"])` in-process should not
    find them ASCII afterwards. What decides is the stream's encoding, which is
    what Python writes with — not what the terminal on the other end expects.
    """
    changed = []
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        before = (stream.encoding, stream.errors)
        try:
            is_utf8 = codecs.lookup(stream.encoding or "ascii").name.startswith("utf-8")
            if is_utf8:
                reconfigure(errors="backslashreplace")
            else:
                reconfigure(encoding="ascii", errors="backslashreplace")
        except (LookupError, ValueError, OSError):
            continue
        changed.append((stream, before))
    try:
        yield
    finally:
        for stream, (encoding, errors) in changed:
            with contextlib.suppress(LookupError, ValueError, OSError):
                stream.flush()
                stream.reconfigure(encoding=encoding, errors=errors)


def _cmd_doctor(args: argparse.Namespace) -> None:
    """Report every delivery channel, then exit with the summary status.

    Human-readable only. `--format json` was deliberately left out, which makes
    the exit status the machine-readable half of this command: 0 healthy,
    1 something is broken, 2 something could not be determined.
    """
    with _confined_doctor_output():
        _report_doctor(args)


def _report_doctor(args: argparse.Namespace) -> None:
    # `os.path.isdir`, not `Path.is_dir()`: 3.11-3.13 raise on a path through a
    # directory this process cannot enter — and a link on the way to the
    # project can put one there — which ended `doctor` in a traceback before a
    # channel was looked at. Either way nothing can be inspected.
    if args.project_dir is not None and not os.path.isdir(args.project_dir):
        # Every channel would read as `absent` against a directory that is not
        # there, and absent is healthy — so a mistyped path would be answered
        # with "everything is fine". Nothing was inspected, so the status says
        # exactly that, via the same rule an empty report set uses.
        print(
            f"{_printable(str(args.project_dir))} is not a directory; nothing was inspected.",
            file=sys.stderr,
        )
        print(
            "Check the path, or omit --project-dir to use the nearest project root.",
            file=sys.stderr,
        )
        sys.exit(summarize([]))

    reports = diagnose_all(args.project_dir, run_interpreter=args.run_interpreter)
    width = max((len(report.channel) for report in reports), default=0)
    for report in reports:
        print(f"{report.channel:<{width}}  {report.state:<8}  {_printable(report.detail)}")
        if report.fix:
            print(f"{' ' * width}  {' ' * 8}  -> {_printable(report.fix)}")
    if args.project_dir is not None:
        # Setup registers MCP in user scope by default, and no --project-dir
        # narrows that. Three channels answer for the given project and one
        # answers globally, so the mixed answer is labelled rather than left
        # for the reader to infer.
        print(
            "\nNote: --project-dir selects where the Skills/Rules/hook are looked up."
            " The MCP registration is resolved the way Claude Code resolves it,"
            " which is user scope unless a project-local one shadows it."
        )
    sys.exit(summarize(reports))


def _cmd_check(args: argparse.Namespace) -> None:
    index = build_index()
    resolution = _python_resolution(args)
    dependency_context = _dependency_context(args)
    coverage = detection_coverage(
        index,
        python_version=resolution.version,
        dependency_context=dependency_context,
    )
    try:
        matches = check_file(
            args.file,
            index,
            python_version=resolution.version,
            dependency_context=dependency_context,
        )
    except CheckError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    fmt = _resolve_format(args)

    if fmt == "json":
        _check_json(matches, args.file, resolution, coverage)
    elif not (args.quiet and not matches):
        print(_target_python_heading(resolution))
        _check_human(matches, coverage)

    if matches and not args.exit_zero:
        sys.exit(1)


def _check_json(
    matches: list[CheckMatch],
    file_path: Path,
    resolution: PythonVersionResolution,
    coverage: DetectionCoverage,
) -> None:
    guide_ids = {m.guide_id for m in matches}
    out = {
        "file": str(file_path),
        "mpg_version": __version__,
        "target_python": resolution.as_dict(),
        "matches": [
            {
                "line": m.line,
                "source_line": m.source_line,
                "guide_id": m.guide_id,
                "guide_title": m.guide_title,
                "category": m.category,
                "frequency": m.frequency,
                "snippet": m.snippet,
                "dependency_compatibility": {
                    "status": m.dependency_status,
                    "reasons": list(m.dependency_reasons),
                },
            }
            for m in matches
        ],
        "summary": {
            "total_matches": len(matches),
            "unique_guides": len(guide_ids),
            "guide_ids": sorted(guide_ids),
            "coverage": coverage.as_dict(),
        },
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _check_human(matches: list[CheckMatch], coverage: DetectionCoverage) -> None:
    print(_check_scope_line(coverage))
    if not matches:
        print("No outdated patterns found.")
        return

    for m in matches:
        src = sanitize_line(m.source_line.strip())
        print(f"{m.guide_id:<40} line {m.line}: {src}")
        if m.snippet:
            snip = sanitize_line(m.snippet)
            print(f"{'':40}   {snip}")
        if m.dependency_status != "confirmed":
            reason = (
                m.dependency_reasons[0] if m.dependency_reasons else "dependency status unknown"
            )
            print(f"{'':40}   [deps: {m.dependency_status}] {reason}")

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
    """Wrapper enforcing the hook contract: zero stderr output for clean files.

    detect_* helpers log warnings on malformed config, and an unconfigured
    logging setup routes them to stderr via the last-resort handler, so the
    package logger is silenced for the whole hook run (restored afterwards —
    tests invoke this in-process).
    """
    pkg_logger = logging.getLogger("modern_python_guidance")
    previous_level = pkg_logger.level
    pkg_logger.setLevel(logging.CRITICAL + 1)
    try:
        _hook_post_tool_use_inner()
    finally:
        pkg_logger.setLevel(previous_level)


_MAX_SURFACED_MATCHES = 5

# "Nothing there": the only stat() failures the hook keeps silent, at the gate
# and again in `_hook_not_checked`. Every other errno is a file it cannot reach.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR)


def _hook_post_tool_use_inner() -> None:
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
    try:
        mode = path.stat().st_mode
    except ValueError:
        # A NUL byte or an unencodable surrogate: no filesystem holds a file by
        # this name, so this is "nothing there", like ENOENT. `is_file()` folded
        # these into False on every version; `stat()` raises.
        sys.exit(0)
    except OSError as exc:
        if exc.errno in _ABSENT_ERRNOS:
            sys.exit(0)
        # EACCES, ENAMETOOLONG, ELOOP...: something may be there and the hook
        # cannot reach it. `is_file()` raised here on 3.11-3.13 (a traceback,
        # of which Claude Code shows only the first line) and answered False
        # on 3.14 (silence); `stat()` behaves the same on every version.
        _hook_not_checked(path, exc)
    if not stat.S_ISREG(mode):
        sys.exit(0)

    resolution = _resolve_python_for_file(path)

    try:
        index = build_index()
        if not index.guides:
            # `build_index()` never raises: a missing or hollow guides
            # directory is logged (silenced here) and comes back empty, and
            # an empty catalog finds nothing in any file — the one shape of
            # a broken install that reads exactly like a clean file.
            # Not "see `mpg doctor`": its skills channel reads `SKILL.md`, not
            # the guides beside it, and would call this install `present`.
            raise _HookCannotCheck("the bundled guide catalog loaded no guides; reinstall mpg")
        dependency_context = find_dependency_context(path.resolve().parent)
        coverage = detection_coverage(
            index,
            python_version=resolution.version,
            dependency_context=dependency_context,
        )
        matches = check_file(
            path,
            index,
            python_version=resolution.version,
            dependency_context=dependency_context,
        )
    except Exception as exc:
        # A hook must never break an edit. Until #209 it kept that promise by
        # exiting 0 in silence, indistinguishable from a clean file; it now
        # says so. Broad on purpose, around the check itself: a detector
        # raising ended in a traceback before, of which Claude Code shows
        # only the first line, and the message keeps the exception's type.
        _hook_not_checked(path, exc)

    if not matches:
        sys.exit(0)

    context = _format_hook_context(matches, resolution, coverage)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            }
        )
    )
    sys.exit(0)


class _HookCannotCheck(Exception):
    """A failure the hook diagnosed itself, inside its guard.

    Shown as its text alone: no type name, which foreign exceptions carry so
    a bug stays visible, and no `mpg check` hint, which would not reproduce
    it — `check` with an empty catalog reports a clean file.
    """


def _hook_not_checked(path: Path, exc: BaseException) -> NoReturn:
    """Tell the user, not Claude, that this file was not checked; exit 0.

    Until #209 a file the hook could not check and a clean file were
    byte-identical: nothing on stdout or stderr, exit 0. `systemMessage` is the
    field Claude Code shows to the user; nothing reaches Claude's context, and
    the edit is never blocked. Stderr is not used because on exit 0 it reaches
    only the debug log. `mpg check` is named only for a CheckError, the
    failures `check` reproduces on stderr; for the rest `check` ends in a
    traceback of its own.

    Every character that could act on a terminal is shown as an escape
    (`_printable`, the function `doctor` writes through since #245), and the
    JSON stays ASCII, so a path or an OS message cannot add a line or redraw
    one — the value stays one line.

    A file that vanished after the gate let it through arrives here as
    "file not found", since the check opens it again, and one replaced by a
    directory as "not a file". Both are what the gate keeps silent — nothing
    there, or nothing that is a regular file — so they are silent here too.
    """
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            sys.exit(0)
    except OSError as now:
        if now.errno in _ABSENT_ERRNOS:
            sys.exit(0)
    detail = str(exc)
    if isinstance(exc, (CheckError, _HookCannotCheck)):
        reason = detail
    else:
        reason = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    hint = " `mpg check <file>` reports the same reason." if isinstance(exc, CheckError) else ""
    message = _printable(f"mpg: could not check this file: {reason}.{hint}")
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def _format_hook_context(
    matches: list[CheckMatch],
    resolution: PythonVersionResolution,
    coverage: DetectionCoverage,
) -> str:
    """Build the additionalContext message surfaced to Claude.

    Deliberately excludes raw source lines: the edited file's content is
    attacker-controllable (cloned repo, dependency, PR diff), and echoing it
    back as an authoritative-looking hook message is an indirect prompt
    injection channel. guide_id + line number are mpg's own trusted catalog
    data, sufficient for Claude to look up the modern form.
    """
    shown = matches[:_MAX_SURFACED_MATCHES]
    lines = [_check_scope_line(coverage)]
    lines.extend(f"mpg: {m.guide_id} (line {m.line})" for m in shown)
    remaining = len(matches) - len(shown)
    if remaining > 0:
        lines.append(f"+{remaining} more")

    guide_ids = sorted({m.guide_id for m in matches})
    if any(match.dependency_status == "unknown" for match in matches):
        lines.append(
            f"mpg: {len(matches)} outdated pattern(s) found [target: py{resolution.version}; "
            f"source: {resolution.source}]. "
            "dependency compatibility unknown; verify before applying. Retrieve the guide with "
            f"`{sys.executable} -m modern_python_guidance retrieve {','.join(guide_ids)}` "
            f"or call the MCP tool retrieve_guides({guide_ids})."
        )
    else:
        lines.append(
            f"mpg: {len(matches)} outdated pattern(s) found [target: py{resolution.version}; "
            f"source: {resolution.source}]. "
            f"If these are not intentional, apply the modern form: run "
            f"`{sys.executable} -m modern_python_guidance retrieve {','.join(guide_ids)}` "
            f"or call the MCP tool retrieve_guides({guide_ids})."
        )
    return "\n".join(lines)


def _check_scope_line(coverage) -> str:
    return (
        f"Check scope: {coverage.detectable_count} detectable / "
        f"{coverage.applicable_guides} applicable guides; "
        f"{coverage.advisory_only_count} advisory-only."
    )


def _dependency_context(args: argparse.Namespace) -> DependencyContext:
    return find_dependency_context(args.project_dir, getattr(args, "dependency_overrides", None))


def _python_resolution(args: argparse.Namespace) -> PythonVersionResolution:
    return resolve_python_version(
        explicit_version=getattr(args, "python_version", None),
        project_dir=getattr(args, "project_dir", None),
    )


def _target_python_heading(resolution: PythonVersionResolution) -> str:
    return f"Target Python: {resolution.version} (source: {resolution.source})"


def _assess_meta(packages: list[str], tools: list[str], context: DependencyContext):
    return assess_dependencies(
        package_requirements=packages, tool_requirements=tools, context=context
    )


def _dependency_json(packages: list[str], tools: list[str], assessment: object) -> dict:
    return {
        "dependency_requirements": {"packages": list(packages), "tools": list(tools)},
        "dependency_compatibility": {
            "status": assessment.status,
            "evidence": [
                {
                    "kind": fact.kind,
                    "name": fact.name,
                    "version": fact.version,
                    "specifier": fact.specifier,
                    "source": fact.source,
                }
                for fact in assessment.evidence
            ],
            "reasons": list(assessment.reasons),
        },
    }


def _human_dependency_suffix(status: str, reasons: tuple[str, ...]) -> str:
    if status == "confirmed":
        return " [deps: confirmed]"
    reason = f" {reasons[0]}" if reasons else ""
    return f" [deps: {status}]{reason}"


def _resolve_python_for_file(file_path: Path) -> PythonVersionResolution:
    """Resolve the edited file and find the nearest usable version config.

    Catch-all by design: the walk reads ancestor directories the project does
    not control, and no config anomaly (encoding, parser recursion, symlink
    races — RuntimeError on 3.11/3.12 resolve()) may crash the hook. Any
    failure falls back to the caller's default.
    """
    try:
        start = file_path.resolve().parent
        return resolve_python_version(project_dir=start)
    except Exception:
        return PythonVersionResolution(DEFAULT_VERSION, "default")
