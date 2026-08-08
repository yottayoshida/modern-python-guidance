"""Reverse `mpg setup`: deregister the MCP server and remove the Skills symlink."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from modern_python_guidance.hook_config import (
    remove_hook,
    settings_local_path,
    symlinked_parent_notes,
)
from modern_python_guidance.setup_cmd import (
    MCP_SERVER_NAME,
    _find_project_root,
    _resolve_cwd,
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


def uninstall_mcp(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Deregister the MCP server from Claude Code. Returns True on success.

    Removes the server from every scope `mpg setup` can write to (user, local),
    since the scope used at setup time is not tracked. Idempotent: scopes where
    the server is absent are a no-op. When an explicit project directory is
    unavailable, local cleanup fails closed instead of inheriting the caller's
    cwd; the independent user-scope cleanup is still attempted.
    """
    local_cwd = _resolve_cwd(project_dir)
    local_target_unavailable = project_dir is not None and local_cwd is None

    if dry_run:
        if local_target_unavailable:
            print(
                "Error: cannot preview local MCP removal because the explicit "
                f"--project-dir '{project_dir}' is unavailable. Restore or create "
                "the directory, then rerun 'mpg uninstall'.",
                file=sys.stderr,
            )
        else:
            local_where = f" in {local_cwd}" if local_cwd is not None else ""
            print(f"Would run{local_where}: claude mcp remove {MCP_SERVER_NAME} -s local")
        print(f"Would run: claude mcp remove {MCP_SERVER_NAME} -s user")
        return not local_target_unavailable

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
    local_failed = False
    for scope in _REMOVE_SCOPES:
        if scope == "local" and local_target_unavailable:
            print(
                "Error: cannot remove the local MCP registration because the explicit "
                f"--project-dir '{project_dir}' is unavailable. Restore or create "
                "the directory, then rerun 'mpg uninstall'.",
                file=sys.stderr,
            )
            local_failed = True
            continue

        cmd = [claude, "mcp", "remove", MCP_SERVER_NAME, "-s", scope]
        cwd = local_cwd if scope == "local" else None
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30, cwd=cwd)
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
            if scope == "local" and project_dir is not None and not project_dir.is_dir():
                local_failed = True
                continue
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

    if local_failed:
        print(
            "MCP server cleanup incomplete; the unavailable local scope was not touched.",
            file=sys.stderr,
        )
        return False
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


def uninstall_hook(
    *,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Remove the mpg PostToolUse hook. Returns True on success.

    Idempotent: a no-op success if no mpg hook is registered. Symmetric
    with setup_hook — thin wrapper around hook_config.remove_hook, kept
    here for naming consistency with uninstall_mcp/skills/rules.
    """
    root = project_dir or _find_project_root()
    return remove_hook(project_root=root, dry_run=dry_run)


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
    do_hook = not mcp_only

    # Mirror of run_setup: before touching anything, name every directory being
    # cleaned through that is a symlink, so the tree actually being modified is
    # visible. `do_hook` (identical to do_skills/do_rules) is exactly "this run
    # touches `.claude`"; `--mcp-only` touches nothing there and gets no note —
    # and no project-root walk either.
    if do_hook:
        root = project_dir or _find_project_root()
        for note in symlinked_parent_notes(
            root,
            [
                _skills_link_path(root),
                _rules_file_path(root),
                settings_local_path(root),
            ],
        ):
            print(note)

    mcp_ok = True
    skills_ok = True
    rules_ok = True
    hook_ok = True

    if do_mcp:
        mcp_ok = uninstall_mcp(project_dir=project_dir, dry_run=dry_run)

    if do_skills:
        skills_ok = uninstall_skills(project_dir=project_dir, dry_run=dry_run)

    if do_rules:
        rules_ok = uninstall_rules(project_dir=project_dir, dry_run=dry_run)

    if do_hook:
        hook_ok = uninstall_hook(project_dir=project_dir, dry_run=dry_run)

    if mcp_ok and skills_ok and rules_ok and hook_ok:
        if not dry_run and do_mcp and do_skills:
            print("Done. mpg has been removed.")
        return 0

    return 1
