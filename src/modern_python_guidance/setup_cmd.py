"""Automate MCP server registration and Agent Skills symlink creation."""

from __future__ import annotations

import importlib.resources
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS_LINK_NAME = "modern-python-guidance"
MCP_SERVER_NAME = "mpg"


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


def _find_project_root(start: Path | None = None) -> Path:
    """Walk upward from *start* to find the project root."""
    current = (start or Path.cwd()).resolve()
    markers = [".claude", ".git", "pyproject.toml"]

    for marker in markers:
        d = current
        while True:
            candidate = d / marker
            if candidate.exists():
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


def setup_mcp(
    *,
    scope: str = "user",
    dry_run: bool = False,
) -> bool:
    """Register the MCP server with Claude Code. Returns True on success."""
    args = ["mcp", "add", "--scope", scope, MCP_SERVER_NAME, "--", "mpg", "mcp"]

    if dry_run:
        print(f"Would run: claude {' '.join(args)}")
        return True

    claude = shutil.which("claude")
    if claude is None:
        print("Error: 'claude' command not found.", file=sys.stderr)
        print("Install Claude Code: https://claude.ai/download", file=sys.stderr)
        print(
            "Run 'mpg setup --skills-only' to set up Agent Skills without MCP.",
            file=sys.stderr,
        )
        return False

    cmd = [claude, *args]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        print("Error: 'claude mcp add' timed out after 30 seconds.", file=sys.stderr)
        return False

    if result.returncode != 0:
        stderr_text = result.stderr.decode(errors="replace").strip()
        print(f"Error: 'claude mcp add' failed (exit {result.returncode}).", file=sys.stderr)
        if stderr_text:
            print(stderr_text, file=sys.stderr)
        return False

    print(f"MCP server registered with Claude Code ({scope} scope).")
    return True


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
        print(
            f"Error: {link_path.relative_to(root)} exists and is not a symlink.",
            file=sys.stderr,
        )
        print(
            f"Remove it manually: rm -rf {shlex.quote(str(link_path))}",
            file=sys.stderr,
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


def run_setup(
    *,
    scope: str = "user",
    mcp_only: bool = False,
    skills_only: bool = False,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Run the full setup sequence. Returns exit code (0=success, 1=failure)."""
    if mcp_only and skills_only:
        print("Error: --mcp-only and --skills-only are mutually exclusive.", file=sys.stderr)
        return 1

    do_mcp = not skills_only
    do_skills = not mcp_only

    mcp_ok = True
    skills_ok = True

    if do_mcp:
        mcp_ok = setup_mcp(scope=scope, dry_run=dry_run)

    if do_skills:
        skills_ok = setup_skills(project_dir=project_dir, dry_run=dry_run)

    if mcp_ok and skills_ok:
        if not dry_run and do_mcp and do_skills:
            print("Ready. Start Claude Code to use mpg guides.")
        return 0

    return 1
