"""Automate MCP server registration and Agent Skills symlink creation."""

from __future__ import annotations

import importlib.resources
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from modern_python_guidance.hook_config import (
    HookConfigError,
    build_mpg_group,
    has_mpg_hook,
    is_ephemeral_interpreter,
    merge_hook,
    read_settings,
    remove_hook,
    settings_local_path,
    write_settings_atomic,
)

SKILLS_LINK_NAME = "modern-python-guidance"
RULE_FILE_NAME = "modern-python.md"
MCP_SERVER_NAME = "mpg"

RULE_FRONTMATTER = (
    "---\n"
    'paths: ["**/*.py", "*.py", "**/pyproject.toml", "**/requirements*.txt",'
    ' "**/setup.py", "**/setup.cfg", "**/.python-version", "**/Pipfile"]\n'
    "---"
)


def _find_skills_dir() -> Path:
    """Resolve the bundled skills directory (package install or editable)."""
    try:
        pkg = importlib.resources.files("modern_python_guidance") / "skills"
        skills_path = Path(str(pkg)) / SKILLS_LINK_NAME
        if skills_path.is_dir():
            return skills_path
    except (TypeError, FileNotFoundError):
        pass

    src_root = Path(__file__).resolve().parent.parent.parent
    dev_path = src_root / "skills" / SKILLS_LINK_NAME
    if dev_path.is_dir():
        return dev_path

    msg = "Cannot locate bundled skills directory"
    raise FileNotFoundError(msg)


def _find_rule_source() -> Path:
    """Resolve the bundled rule file (package install or editable)."""
    try:
        pkg = importlib.resources.files("modern_python_guidance") / "rules"
        rule_path = Path(str(pkg)) / RULE_FILE_NAME
        if rule_path.is_file():
            return rule_path
    except (TypeError, FileNotFoundError):
        pass

    src_root = Path(__file__).resolve().parent.parent.parent
    dev_path = src_root / "rules" / RULE_FILE_NAME
    if dev_path.is_file():
        return dev_path

    msg = "Cannot locate bundled rule file"
    raise FileNotFoundError(msg)


def _find_project_root(start: Path | None = None) -> Path:
    """Walk upward; return the nearest ancestor containing any marker."""
    current = (start or Path.cwd()).resolve()
    markers = [".git", "pyproject.toml", ".claude"]

    d = current
    while True:
        for marker in markers:
            if (d / marker).exists():
                return d
        parent = d.parent
        if parent == d:
            break
        d = parent

    return current


def _skills_link_path(project_dir: Path | None = None) -> Path:
    """Resolve the Agent Skills symlink path: ``<root>/.claude/skills/<name>``.

    Single source of truth for where the skills symlink lives, shared by
    ``setup_skills`` (creation) and ``uninstall_skills`` (removal) so the two
    operations cannot drift in how they locate the link.
    """
    root = project_dir or _find_project_root()
    return root / ".claude" / "skills" / SKILLS_LINK_NAME


def _rules_file_path(project_dir: Path | None = None) -> Path:
    """Resolve the rule file symlink path: ``<root>/.claude/rules/modern-python.md``."""
    root = project_dir or _find_project_root()
    return root / ".claude" / "rules" / RULE_FILE_NAME


_THIN_RULE_BODY = """\
# Modern Python Guidance

Pre-generation design patterns that Ruff cannot auto-fix. Apply these transformations when writing or reviewing Python code.

## Dependency applicability

Before a framework or tool pattern, inspect project evidence or explicit overrides with `mcp__mpg__search_guides` / `retrieve_guides` (or `mpg search ... --project-dir . --dependency-version KIND:NAME=VERSION`). Requirements use AND semantics: `confirmed` means every requirement is proven; unknown is not confirmation, so verify before changing code; never auto-apply known-incompatible guidance. Do not use mpg's interpreter, optional/group declarations, or an ambiguous lockfile as proof.

## Embedded patterns (high-frequency, Ruff-uncovered)

- `from typing import List, Dict` → `list[str]`, `dict[str, int]` (>=3.9)
- `@validator("f")` → `@field_validator("f")` (Pydantic V2)
- `datetime.utcnow()` → `datetime.now(UTC)` (>=3.11)
- `session.query(User).filter()` → `session.execute(select(User).where())` (SQLAlchemy 2.0)
- `subprocess.run(f"cmd {arg}", shell=True)` → `subprocess.run(["cmd", arg], check=True)`

## Beyond these 5 patterns

Writing Python outside them (FastAPI, Django, httpx, pytest, or anything in the 41-guide catalog below)? Call `mcp__mpg__search_guides` before committing to a pattern.

## All 41 guides by category

- **async** (3): `async-timeout-context`, `exception-groups`, `taskgroup-over-gather`
- **data-structures** (3): `dataclass-modern`, `dict-merge-operator`, `match-case-patterns`
- **django** (3): `django-async-views`, `django-check-constraints`, `django-json-field`
- **fastapi** (3): `fastapi-annotated-depends`, `fastapi-lifespan`, `fastapi-typed-state`
- **httpx** (2): `httpx-async-client-reuse`, `httpx-streaming`
- **pydantic** (4): `pydantic-v2-config`, `pydantic-v2-model-api`, `pydantic-v2-serialization`, `pydantic-v2-validators`
- **pytest** (3): `pytest-parametrize`, `pytest-raises-match`, `pytest-tmp-path`
- **sqlalchemy** (3): `sqlalchemy-2-style`, `sqlalchemy-async-session`, `sqlalchemy-mapped-column`
- **stdlib** (5): `datetime-utc`, `pathlib-over-os-path`, `removeprefix-removesuffix`, `template-strings`, `tomllib-builtin`
- **toolchain** (5): `no-pickle`, `pyproject-toml-over-setup`, `ruff-over-flake8`, `safe-subprocess`, `uv-over-pip`
- **typing** (7): `deferred-annotations`, `override-decorator`, `paramspec-decorators`, `type-parameter-syntax`, `typeis-vs-typeguard`, `union-syntax`, `use-builtin-generics`

For full code examples, use `mpg retrieve <guide-id>` or MCP tool `retrieve_guides`.
"""


def _build_rule_text() -> str:
    """Generate thin rule file content with category index and MCP pointer."""
    return RULE_FRONTMATTER + "\n\n" + _THIN_RULE_BODY


def _run_claude_mcp(
    cmd: list[str], cwd: str | None = None
) -> subprocess.CompletedProcess[bytes] | None:
    """Run a claude mcp subcommand; report timeout/OSError and return None."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30, cwd=cwd)
    except subprocess.TimeoutExpired:
        print("Error: 'claude mcp' command timed out after 30 seconds.", file=sys.stderr)
        return None
    except OSError as e:
        print(f"Error: failed to run 'claude mcp' command: {e}", file=sys.stderr)
        return None


def _print_stderr(result: subprocess.CompletedProcess[bytes]) -> None:
    stderr_text = (result.stderr or b"").decode(errors="replace").strip()
    if stderr_text:
        print(stderr_text, file=sys.stderr)


def _run_claude_mcp_quiet(
    cmd: list[str], cwd: str | None = None
) -> subprocess.CompletedProcess[bytes] | None:
    """Run a claude mcp subcommand without reporting failures.

    For advisory paths (shadowing detection) where an ``Error:`` line right
    after a successful setup would be misleading; callers degrade instead.
    """
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30, cwd=cwd)
    except (subprocess.TimeoutExpired, OSError):
        return None


# Claude Code resolves same-name MCP registrations by scope precedence
# (the whole entry from the highest-precedence scope wins; no merging).
_SCOPE_PRECEDENCE = {"local": 3, "project": 2, "user": 1}


def _effective_scope(stdout: bytes) -> str | None:
    """Extract the winning scope from ``claude mcp get`` output.

    Returns "local"/"project"/"user", or None when the ``Scope:`` line is
    missing or names an unknown scope (e.g. the claude.ai-managed scope, or
    a future format change) — callers must stay silent then, because a
    wrong warning would prompt the user to remove a healthy registration.
    """
    for line in stdout.decode(errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("Scope:"):
            rest = stripped.removeprefix("Scope:").strip()
            token = rest.split()[0].lower() if rest else ""
            return token if token in _SCOPE_PRECEDENCE else None
    return None


def _resolve_cwd(project_dir: Path | None) -> str | None:
    """Resolve the subprocess cwd for project-bound ``claude mcp`` calls.

    Local/project scopes are bound to the project directory ``claude`` runs
    in, so every ``claude mcp`` call setup issues (add, remove, retry-add,
    and the advisory shadow check) must share this same resolution — a
    second, independent computation is how #164 happened (the shadow check
    ran in ``project_dir`` while add/remove silently inherited the caller's
    cwd instead).

    Returns None (inherit the caller's cwd) when no ``--project-dir`` was
    given, or when the given path doesn't exist yet (nothing to cwd into).
    """
    return str(project_dir) if project_dir is not None and project_dir.is_dir() else None


def _prepare_project_dir(
    project_dir: Path | None,
    *,
    required: bool,
    dry_run: bool,
) -> bool:
    """Ensure a required project target exists before any external mutation."""
    if not required or project_dir is None:
        return True

    if project_dir.exists():
        if project_dir.is_dir():
            return True
        print(
            f"Error: project directory '{project_dir}' exists but is not a directory.",
            file=sys.stderr,
        )
        return False

    print(
        f"Warning: directory '{project_dir}' does not exist and will be created.",
        file=sys.stderr,
    )
    if dry_run:
        return True

    try:
        project_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error: failed to create project directory '{project_dir}': {e}", file=sys.stderr)
        return False
    return True


def _warn_if_shadowed(scope: str, claude: str, cwd: str | None) -> None:
    """Warn when a higher-precedence scope shadows the entry just written.

    Advisory only: never changes setup's outcome, and never issues mutating
    ``claude mcp`` subcommands. Failure handling is asymmetric on purpose:
    a get failure right after a successful add is anomalous and gets a
    one-line note (without a remove command), while unparseable output is
    silently skipped (#131).
    """
    if scope not in _SCOPE_PRECEDENCE:
        return
    result = _run_claude_mcp_quiet([claude, "mcp", "get", MCP_SERVER_NAME], cwd=cwd)
    if result is None or result.returncode != 0:
        print(
            f"Note: could not verify which scope's '{MCP_SERVER_NAME}' registration "
            f"Claude Code will launch. Inspect with: claude mcp get {MCP_SERVER_NAME}",
            file=sys.stderr,
        )
        return
    winner = _effective_scope(result.stdout or b"")
    if winner is None or _SCOPE_PRECEDENCE[winner] <= _SCOPE_PRECEDENCE[scope]:
        return
    print(
        f"Warning: an existing '{MCP_SERVER_NAME}' MCP registration in the "
        f"higher-precedence '{winner}' scope will be used instead of the "
        f"'{scope}'-scope one just registered.",
        file=sys.stderr,
    )
    print(
        "Claude Code resolves scopes local > project > user. If that entry points "
        "at an old or broken command, mpg guides will silently fail to load.",
        file=sys.stderr,
    )
    print(
        "To use the new registration, remove the shadowing entry and re-run setup:",
        file=sys.stderr,
    )
    print(f"  claude mcp remove {MCP_SERVER_NAME} -s {winner}", file=sys.stderr)
    print("  mpg setup", file=sys.stderr)


def setup_mcp(
    *,
    scope: str = "user",
    dry_run: bool = False,
    project_dir: Path | None = None,
) -> bool:
    """Register the MCP server with Claude Code. Returns True on success.

    The launch command pins the current interpreter (``sys.executable -m ...``)
    instead of a bare ``mpg``: Claude Code spawns MCP servers from its own
    environment, where a venv-only ``mpg`` is not on PATH (#118).
    """
    if not sys.executable or not Path(sys.executable).is_file():
        # sys.executable can be empty in embedded/frozen interpreters; a
        # registration pointing at it would never launch.
        print("Error: cannot resolve the current Python interpreter path.", file=sys.stderr)
        print(
            "Re-run 'mpg setup' from a regular Python environment "
            "(frozen/embedded interpreters cannot host the MCP server).",
            file=sys.stderr,
        )
        return False

    launch = [sys.executable, "-m", "modern_python_guidance", "mcp"]
    args = ["mcp", "add", "--scope", scope, MCP_SERVER_NAME, "--", *launch]
    if scope == "local":
        cwd = _resolve_cwd(project_dir)
        if project_dir is not None and cwd is None:
            if dry_run:
                cwd = str(project_dir)
            else:
                print(
                    "Error: local MCP registration requires an existing directory for "
                    f"--project-dir '{project_dir}'. Run 'mpg setup' to create it "
                    "before registering the local server.",
                    file=sys.stderr,
                )
                return False
    else:
        cwd = None

    if dry_run:
        where = f" in {cwd}" if cwd is not None else ""
        print(f"Would run{where}: claude {shlex.join(args)}")
        return True

    claude = shutil.which("claude")
    if claude is None:
        print("Error: 'claude' command not found.", file=sys.stderr)
        print("Install Claude Code: https://claude.ai/download", file=sys.stderr)
        print(
            "Run 'mpg setup --skills-only' to set up project-local artifacts without MCP.",
            file=sys.stderr,
        )
        return False

    add_cmd = [claude, *args]
    result = _run_claude_mcp(add_cmd, cwd=cwd)
    if result is None:
        return False

    if result.returncode != 0 and b"already exists" in (result.stderr or b""):
        # Stale registration (e.g. a pre-#118 bare `mpg` entry): replace it.
        # Add-first keeps the existing entry intact when `add` fails for any
        # other reason (timeout, permissions), so a broken retry cannot leave
        # the user with no registration at all.
        remove_cmd = [claude, "mcp", "remove", "--scope", scope, MCP_SERVER_NAME]
        removed = _run_claude_mcp(remove_cmd, cwd=cwd)
        if removed is None or removed.returncode != 0:
            print(
                f"Error: could not replace the existing '{MCP_SERVER_NAME}' registration.",
                file=sys.stderr,
            )
            if removed is not None:
                _print_stderr(removed)
            return False
        result = _run_claude_mcp(add_cmd, cwd=cwd)
        if result is None:
            return False

    if result.returncode != 0:
        print(f"Error: 'claude mcp add' failed (exit {result.returncode}).", file=sys.stderr)
        _print_stderr(result)
        # Only reachable when the retried add hit "already exists" again (a
        # race); for unrelated failures a remove suggestion would be harmful.
        if b"already exists" in (result.stderr or b""):
            print(
                f"Run 'claude mcp remove {MCP_SERVER_NAME} --scope {scope}' "
                f"and re-run 'mpg setup'.",
                file=sys.stderr,
            )
        return False

    print(f"MCP server registered with Claude Code ({scope} scope).")
    print(f"Registered launch: {shlex.join(launch)}")
    _warn_if_shadowed(scope, claude, cwd)
    return True


def _print_flattened_symlink_error(
    link_path: Path,
    root: Path,
    *,
    kind: str,
    remove_cmd: str,
    extra_note: str = "",
) -> None:
    """Shared migration-guidance message for setup_skills/setup_rules when a
    non-symlink occupies the path mpg manages.

    A common real-world cause is a symlink flattened into a real file/dir by
    tooling that doesn't preserve symlinks (git checkout on some platforms,
    backup/sync scripts) — not an old mpg version writing content directly,
    since both delivery paths have been symlink-only since their
    introduction. Shared between the two call sites so the wording can't
    drift the way #164's duplicated cwd computation did.
    """
    print(f"Error: {link_path.relative_to(root)} exists and is not a symlink.", file=sys.stderr)
    print(
        f"This {kind} is not a symlink mpg manages. A common cause is a "
        f"symlink that got flattened into a real {kind} by tooling that "
        f"doesn't preserve symlinks (git checkout on some platforms, "
        f"backup/sync scripts).{extra_note}",
        file=sys.stderr,
    )
    print(f"Remove it manually: {remove_cmd}", file=sys.stderr)
    print("Then re-run: mpg setup", file=sys.stderr)


def setup_skills(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Create Agent Skills symlink. Returns True on success."""
    try:
        source = _find_skills_dir()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

    root = project_dir or _find_project_root()
    link_path = _skills_link_path(project_dir)
    skills_parent = link_path.parent

    if dry_run:
        print(f"Would link: {link_path} -> {source}")
        return True

    if link_path.is_symlink():
        current_target = Path(os.readlink(link_path))
        if current_target == source or link_path.resolve() == source.resolve():
            print(f"Agent Skills already linked at {link_path.relative_to(root)}")
            return True
        # Stale or broken symlink — replace
        link_path.unlink()
    elif link_path.exists():
        _print_flattened_symlink_error(
            link_path,
            root,
            kind="path",
            remove_cmd=f"rm -rf {shlex.quote(str(link_path))}",
        )
        return False

    try:
        skills_parent.mkdir(parents=True, exist_ok=True)
        os.symlink(source, link_path)
    except OSError as e:
        print(f"Error creating symlink: {e}", file=sys.stderr)
        return False

    print(f"Agent Skills linked to {link_path.relative_to(root)}")
    return True


def setup_rules(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Create a rule file symlink. Returns True on success."""
    try:
        source = _find_rule_source()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

    if source.is_symlink():
        print("Error: rule source is itself a symlink (unexpected).", file=sys.stderr)
        return False

    root = project_dir or _find_project_root()
    link_path = _rules_file_path(project_dir)
    rules_parent = link_path.parent

    if dry_run:
        print(f"Would link: {link_path} -> {source}")
        return True

    if link_path.is_symlink():
        current_target = Path(os.readlink(link_path))
        if current_target == source or link_path.resolve() == source.resolve():
            print(f"Rule already linked at {link_path.relative_to(root)}")
            return True
        link_path.unlink()
    elif link_path.exists():
        _print_flattened_symlink_error(
            link_path,
            root,
            kind="file",
            remove_cmd=f"rm {shlex.quote(str(link_path))}",
            extra_note=(
                " Its content will be replaced by the up-to-date rule once removed and re-linked."
            ),
        )
        return False

    try:
        rules_parent.mkdir(parents=True, exist_ok=True)
        os.symlink(source, link_path)
    except OSError as e:
        print(f"Error creating symlink: {e}", file=sys.stderr)
        return False

    print(f"Rule linked to {link_path.relative_to(root)}")
    return True


def _has_existing_assets(project_dir: Path | None = None) -> bool:
    """True if this project already has mpg's Skills or Rules symlink.

    Used to decide whether hook auto-registration would silently change
    behavior for an existing user (guardrail: never flip a project's
    default without an explicit `--with-hook`). Checks project scope only
    — a user-scope MCP registration does not count, since a fresh project
    with an existing user-wide MCP registration is exactly the case the
    hook should default on for.
    """
    return (
        _skills_link_path(project_dir).is_symlink() or _rules_file_path(project_dir).is_symlink()
    )


def setup_hook(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Register the mpg PostToolUse hook. Returns True on success.

    Writes to ``<project_dir>/.claude/settings.local.json`` — a personal,
    git-ignored file, never the shared ``settings.json`` — so this cannot
    change behavior for teammates on ``git pull``. Skipping an ephemeral
    interpreter (uvx/temp venv) is a deliberate no-op, not a failure: a
    hook pinned to a torn-down venv would break on every future edit.
    """
    if not sys.executable or not Path(sys.executable).is_file():
        print("Error: cannot resolve the current Python interpreter path.", file=sys.stderr)
        return False

    if is_ephemeral_interpreter(sys.executable):
        print(
            f"Skipping hook registration: {sys.executable} looks like a "
            "one-shot environment (uvx/temp) that will be torn down, leaving "
            "the hook broken. Install with 'uv tool install' or 'pipx install' "
            "for a persistent environment, then run 'mpg setup --with-hook'.",
            file=sys.stderr,
        )
        return True

    root = project_dir or _find_project_root()
    path = settings_local_path(root)

    try:
        settings = read_settings(path)
        merged = merge_hook(settings, sys.executable)
    except HookConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Hook registration skipped; existing file left untouched.", file=sys.stderr)
        return False

    group = build_mpg_group(sys.executable)

    if dry_run:
        print(f"Would write hook entry to {path}:")
        print(json.dumps(group, indent=2))
        return True

    try:
        write_settings_atomic(path, merged)
    except HookConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Error: failed to write {path}: {e}", file=sys.stderr)
        return False

    print(f"PostToolUse hook registered in {path}")
    print(json.dumps(group, indent=2))
    print("Disable: mpg setup --no-hook")
    return True


def run_setup(
    *,
    scope: str = "user",
    mcp_only: bool = False,
    skills_only: bool = False,
    project_dir: Path | None = None,
    dry_run: bool = False,
    no_hook: bool = False,
    with_hook: bool = False,
) -> int:
    """Run the full setup sequence. Returns exit code (0=success, 1=failure).

    Hook default-on decision (guardrail against silently changing behavior
    for an existing user, #152): if this project already has mpg's Skills
    or Rules symlink, auto-registration is skipped in favor of an
    announcement — an existing user must opt in with ``--with-hook``. A
    fresh project (no prior mpg artifacts) gets the hook by default, since
    an opt-in-only hook is exactly the delivery gap #152 exists to close.
    ``--no-hook`` always wins: it actively removes any existing mpg hook,
    it does not merely skip adding one.
    """
    if mcp_only and skills_only:
        print("Error: --mcp-only and --skills-only are mutually exclusive.", file=sys.stderr)
        return 1
    if no_hook and with_hook:
        print("Error: --no-hook and --with-hook are mutually exclusive.", file=sys.stderr)
        return 1

    do_mcp = not skills_only
    do_skills = not mcp_only
    do_rules = not mcp_only
    do_hook = not mcp_only

    requires_project_dir = do_skills or do_rules or (do_mcp and scope == "local")
    if not _prepare_project_dir(
        project_dir,
        required=requires_project_dir,
        dry_run=dry_run,
    ):
        return 1

    # Resolved once and reused for the existing-asset snapshot, setup_hook,
    # and remove_hook below — each independently re-walks via
    # _find_project_root() when given None, so resolving here collapses
    # what would otherwise be several redundant filesystem walks into one.
    # Snapshotted before setup_skills/setup_rules run: they create the very
    # symlinks the existing-asset guardrail checks for.
    root = (project_dir or _find_project_root()) if do_hook else None
    existing_assets = _has_existing_assets(root) if do_hook else False

    mcp_ok = True
    skills_ok = True
    rules_ok = True
    hook_ok = True

    if do_mcp:
        mcp_ok = setup_mcp(scope=scope, dry_run=dry_run, project_dir=project_dir)

    if do_skills:
        skills_ok = setup_skills(project_dir=project_dir, dry_run=dry_run)

    if do_rules:
        rules_ok = setup_rules(project_dir=project_dir, dry_run=dry_run)

    if do_hook:
        if no_hook:
            hook_ok = remove_hook(project_root=root, dry_run=dry_run)
        elif with_hook or not existing_assets:
            hook_ok = setup_hook(project_dir=root, dry_run=dry_run)
        elif not dry_run:
            # An existing user (existing_assets=True) already has the hook
            # if a prior `--with-hook` run registered it — re-running plain
            # `mpg setup` (e.g. after upgrading) must not re-announce "New:
            # ... Enable" for something already enabled (QA M1).
            try:
                already_registered = has_mpg_hook(read_settings(settings_local_path(root)))
            except HookConfigError:
                already_registered = False
            if not already_registered:
                print("New: mpg can auto-check Python files after every edit.")
                print("Enable: mpg setup --with-hook")

    if mcp_ok and skills_ok and rules_ok and hook_ok:
        if not dry_run and do_mcp and do_skills:
            print("Ready. Start Claude Code to use mpg guides.")
        return 0

    return 1
