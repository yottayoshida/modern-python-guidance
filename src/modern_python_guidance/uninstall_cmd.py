"""Reverse `mpg setup`: deregister the MCP server and remove the Skills symlink."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from modern_python_guidance.setup_cmd import (
    MCP_SERVER_NAME,
    _find_project_root,
    _rules_file_path,
    _skills_link_path,
)

# The scopes `mpg setup --scope {user,local}` can write to. uninstall clears
# both because it does not track which scope setup used. Deterministic
# enumeration is required: `claude mcp remove <name>` WITHOUT a scope does NOT
# remove when the server exists in multiple scopes — it just prints per-scope
# hints (exit 0), removing nothing. Per-scope removal avoids that ambiguity.
_REMOVE_SCOPES = ("local", "user")

# Substring printed by `claude mcp remove <name> -s <scope>` when the server is
# NOT present in that scope, e.g. "No user-scoped MCP server found with name...".
# Per-scope removal returns exit 0 whether it removed or found nothing, so this
# marker is how we tell "removed something" from "was already absent". Matching
# the stable middle of the phrase (not the scope word or quoted name) keeps it
# robust; if the wording changes we over-report "removed", never falsely claim
# clean while leaving residue.
_NOT_IN_SCOPE_MARKER = "-scoped MCP server found"


def uninstall_mcp(*, dry_run: bool = False) -> bool:
    """Deregister the MCP server from Claude Code. Returns True on success.

    Removes the server from every scope `mpg setup` can write to (user, local),
    since the scope used at setup time is not tracked. Idempotent: scopes where
    the server is absent are a no-op.
    """
    if dry_run:
        for scope in _REMOVE_SCOPES:
            print(f"Would run: claude mcp remove {MCP_SERVER_NAME} -s {scope}")
        return True

    claude = shutil.which("claude")
    if claude is None:
        print("Error: 'claude' command not found.", file=sys.stderr)
        print("Install Claude Code: https://claude.ai/download", file=sys.stderr)
        print(
            "Run 'mpg uninstall --skills-only' to remove project-local artifacts without MCP.",
            file=sys.stderr,
        )
        return False

    removed_any = False
    for scope in _REMOVE_SCOPES:
        cmd = [claude, "mcp", "remove", MCP_SERVER_NAME, "-s", scope]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            print(
                f"Error: 'claude mcp remove -s {scope}' timed out after 30 seconds.",
                file=sys.stderr,
            )
            return False
        except OSError as e:
            # `claude` resolved on PATH but could not be executed (broken binary,
            # permissions, platform quirk). Fail gracefully instead of crashing.
            print(f"Error: failed to run 'claude mcp remove -s {scope}': {e}", file=sys.stderr)
            return False

        output = (result.stdout + result.stderr).decode(errors="replace").strip()
        if result.returncode != 0:
            # A genuine failure (permissions, broken CLI, etc.) — do not hide it.
            print(
                f"Error: 'claude mcp remove -s {scope}' failed (exit {result.returncode}).",
                file=sys.stderr,
            )
            if output:
                print(output, file=sys.stderr)
            return False

        if _NOT_IN_SCOPE_MARKER not in output:
            removed_any = True

    if removed_any:
        print("MCP server removed from Claude Code.")
    else:
        print("MCP server not registered — nothing to remove.")
    return True


def uninstall_skills(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Remove the Agent Skills symlink. Returns True on success.

    Safety: only a symlink is removed (`Path.unlink` deletes the link entry,
    never the target). A non-symlink entity at the link path is refused, not
    deleted. The parent `.claude/skills/` directory is left intact.

    Idempotent: if no symlink is present, this is a no-op success.
    """
    root = project_dir or _find_project_root()
    link_path = _skills_link_path(project_dir)

    # Primary gate: is_symlink() is True even for a dangling (broken) symlink,
    # whereas exists() is False for one. We must remove dangling links too.
    if not link_path.is_symlink():
        if link_path.exists():
            # A real file/dir lives here — not ours. Refuse to delete it.
            print(
                f"Error: {link_path.relative_to(root)} exists and is not a symlink.",
                file=sys.stderr,
            )
            print(
                f"Remove it manually: rm -rf {shlex.quote(str(link_path))}",
                file=sys.stderr,
            )
            return False
        # Nothing linked — already clean.
        print(f"Agent Skills not linked at {link_path.relative_to(root)} — nothing to remove.")
        return True

    if dry_run:
        print(f"Would remove: {link_path}")
        return True

    try:
        link_path.unlink()
    except OSError as e:
        print(f"Error removing symlink: {e}", file=sys.stderr)
        return False

    print(f"Agent Skills unlinked from {link_path.relative_to(root)}")
    return True


def uninstall_rules(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Remove the rule file symlink. Returns True on success.

    Only a symlink is removed. A non-symlink entity at the path is refused.
    Idempotent: if no symlink is present, this is a no-op success.
    """
    root = project_dir or _find_project_root()
    link_path = _rules_file_path(project_dir)

    if not link_path.is_symlink():
        if link_path.exists():
            print(
                f"Error: {link_path.relative_to(root)} exists and is not a symlink.",
                file=sys.stderr,
            )
            print(
                f"Remove it manually: rm {shlex.quote(str(link_path))}",
                file=sys.stderr,
            )
            return False
        print(f"Rule not linked at {link_path.relative_to(root)} — nothing to remove.")
        return True

    if dry_run:
        print(f"Would remove: {link_path}")
        return True

    try:
        link_path.unlink()
    except OSError as e:
        print(f"Error removing symlink: {e}", file=sys.stderr)
        return False

    print(f"Rule unlinked from {link_path.relative_to(root)}")
    return True


def run_uninstall(
    *,
    mcp_only: bool = False,
    skills_only: bool = False,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Run the full uninstall sequence. Returns exit code (0=success, 1=failure)."""
    if mcp_only and skills_only:
        print("Error: --mcp-only and --skills-only are mutually exclusive.", file=sys.stderr)
        return 1

    do_mcp = not skills_only
    do_skills = not mcp_only
    do_rules = not mcp_only

    mcp_ok = True
    skills_ok = True
    rules_ok = True

    if do_mcp:
        mcp_ok = uninstall_mcp(dry_run=dry_run)

    if do_skills:
        skills_ok = uninstall_skills(project_dir=project_dir, dry_run=dry_run)

    if do_rules:
        rules_ok = uninstall_rules(project_dir=project_dir, dry_run=dry_run)

    if mcp_ok and skills_ok and rules_ok:
        if not dry_run and do_mcp and do_skills:
            print("Done. mpg has been removed.")
        return 0

    return 1
