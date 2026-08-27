"""Merge/unmerge the mpg PostToolUse hook into Claude Code's settings.local.json.

Unlike MCP registration (delegated to the `claude mcp` CLI, which owns its
own JSON safety), there is no `claude hooks` CLI: this module owns the
entire read/parse/merge/atomic-write contract for the hooks file itself.
Fail-closed throughout — any shape this module cannot safely interpret
leaves the file untouched (see #152 shape enumeration:
`.claude/plans/sprightly-riding-globe-pr2-shapes.md`).
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

HOOK_EVENT = "PostToolUse"
HOOK_SUBCOMMAND = "claude-post-tool-use"
HOOK_MATCHER = "Edit|Write"
SETTINGS_FILE_NAME = "settings.local.json"

# Cache-dir fragments that mark a one-shot `uvx`-style venv: it is torn
# down after the invoking command exits, so a hook pinned to it is a
# pre-broken registration (#152 plan Step 2, uvx/pipx ephemeral guard).
# Substring-anywhere is safe here — these are specific enough (nested
# .cache/uv or uv/cache structure) that a persistent project is unlikely
# to collide with them.
_EPHEMERAL_CACHE_MARKERS = (
    "/.cache/uv/",
    "/uv/cache/",
)

# System temp ROOTS: matched only as a path-segment anchor at the very
# start of the interpreter path, not a substring search — a persistent
# project a user merely named "tmp" (e.g. ~/tmp/my-project/.venv/...)
# must not false-positive just because "tmp" appears somewhere in it.
_EPHEMERAL_PATH_ROOTS = (
    "/tmp/",
    "/private/tmp/",
    "/private/var/folders/",
)


class HookConfigError(Exception):
    """A settings file shape this module cannot safely edit. Fail-closed:
    callers must leave the file untouched when this is raised."""


def _is_mpg_entry(entry: object) -> bool:
    """Identity check: does this hook entry belong to mpg?

    Matches the hook subcommand name (`claude-post-tool-use`) as an exact
    whitespace-separated word of `command`, or as an exact element of
    `args` — never a bare substring search. A substring check over the
    joined `command + args` text is a false-positive hazard: a foreign
    tool with an unrelated log path or argument value that merely
    *contains* the token (e.g. `"...-claude-post-tool-use-related.log"`,
    or a `str()`-coerced dict repr `"{'tag': 'claude-post-tool-use'}"`)
    would be silently adopted as mpg's own group and then overwritten or
    deleted. Exact-word matching still survives both a legacy bare-`mpg`
    registration (README's old manual step, token appears as a word in
    `command`) and the `command`+`args` exec-form split (token is an
    `args` element) — shape enumeration #152-⑤b.
    """
    if not isinstance(entry, dict):
        return False
    command = entry.get("command", "")
    if not isinstance(command, str):
        command = ""
    args = entry.get("args", [])
    if not isinstance(args, list):
        args = []
    return HOOK_SUBCOMMAND in command.split() or HOOK_SUBCOMMAND in args


def _group_has_mpg_entry(group: object) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(_is_mpg_entry(e) for e in hooks)


def build_mpg_hook_entry(python: str) -> dict:
    """The hook entry mpg registers. `command`+`args` split (not a shell
    string) avoids shell-string construction entirely."""
    return {
        "type": "command",
        "command": python,
        "args": ["-m", "modern_python_guidance", "hook", HOOK_SUBCOMMAND],
    }


def build_mpg_group(python: str) -> dict:
    """The PostToolUse group mpg registers (one entry, mpg's own matcher).
    Shared by `merge_hook` and callers that need to know the exact shape
    just written without re-scanning the merged settings for it."""
    return {"matcher": HOOK_MATCHER, "hooks": [build_mpg_hook_entry(python)]}


def find_mpg_entries(settings: dict) -> list[tuple[dict, dict]]:
    """Every (group, entry) pair in `PostToolUse` whose entry belongs to mpg.

    Entry granularity, matching `_strip_mpg_entries`. The writing side has
    always assumed more than one can exist — `merge_hook` promises to converge
    "from ANY starting state ... a settings file that somehow already has 2+
    matching entries/groups" — while the only reader was `find_mpg_group`,
    which stops at the first group. A reader that stops early cannot see a
    second registration at all, and a second registration is exactly the shape
    `merge_hook` was written to clean up.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    post = hooks.get(HOOK_EVENT)
    if not isinstance(post, list):
        return []
    found: list[tuple[dict, dict]] = []
    for group in post:
        # Guarantees `group` is a dict whose `hooks` is a list, so the
        # comprehension below can index it directly — the same guarantee
        # `_strip_mpg_entries` relies on.
        if not _group_has_mpg_entry(group):
            continue
        found.extend((group, entry) for entry in group["hooks"] if _is_mpg_entry(entry))
    return found


def find_mpg_group(settings: dict) -> dict | None:
    """Return mpg's first PostToolUse group if present, else None.

    Defined in terms of `find_mpg_entries` rather than carrying its own scan:
    two traversals of the same structure would be two definitions of "an mpg
    entry", and the one that drifted would be the one nobody read.

    First-match is the right answer for the callers that ask a yes/no question
    (`has_mpg_hook`: is anything registered, is there anything to remove).
    Callers that read *into* what they find want `find_mpg_entries`.
    """
    entries = find_mpg_entries(settings)
    return entries[0][0] if entries else None


def has_mpg_hook(settings: dict) -> bool:
    return find_mpg_group(settings) is not None


# Claude Code decides how to read a matcher from the characters it holds: only
# letters, digits, `_`, `-`, spaces, `,` and `|` make it an exact string (or a
# `|`/`,`-separated list of exact strings); anything else makes it an
# unanchored regular expression. So `Edit|Write` is a two-name list, not an
# alternation — it does not fire for `NotebookEdit`.
_SIMPLE_MATCHER = re.compile(r"[A-Za-z0-9_ ,|-]*")

MATCH_EVERYTHING = (None, "", "*")
"""Matcher values Claude Code treats as "every tool"."""

HOOK_TOOLS: tuple[str, ...] = tuple(HOOK_MATCHER.split("|"))
"""The tools mpg's own matcher names. Derived from `HOOK_MATCHER` so a change
to what mpg registers cannot leave a second list behind saying otherwise."""


def matcher_fires_on(matcher: object, tool: str) -> bool | None:
    """Whether a hook group's `matcher` selects `tool`.

    `None` means the question could not be answered here, and is never folded
    into `False`. Claude Code evaluates the regular-expression form in
    JavaScript; Python's `re` accepts a different language at the edges, so a
    pattern this process cannot compile is one it has not measured. Reporting
    "does not fire" for it would state a result that was never obtained — and
    would call a matcher broken that Claude Code runs perfectly well.
    """
    if matcher in MATCH_EVERYTHING:
        return True
    if not isinstance(matcher, str):
        # A non-string matcher is not something this function can evaluate;
        # saying so is different from saying the hook does not fire.
        return None
    # `fullmatch`, not `match`: Python's `$` also matches just before a trailing
    # newline, so `^...$` calls `"Edit|Write\n"` simple. The newline puts it in
    # the regular-expression form, where `Write` does not match at all — the
    # misclassification turns "does not fire" into "fires", which is the
    # direction this whole change exists to stop.
    if _SIMPLE_MATCHER.fullmatch(matcher):
        names = {part.strip() for part in re.split(r"[|,]", matcher)}
        return tool in names
    try:
        return re.search(matcher, tool) is not None
    except Exception:
        # Not just `re.error`. A large enough repetition count raises
        # `OverflowError` and deep nesting can exhaust the stack, neither of
        # which is an `re.error` — and a matcher out of a settings file is
        # untrusted input, so a narrow `except` here is a way to end `mpg
        # doctor` in a traceback by writing one line of JSON. Everything that
        # goes wrong evaluating it means the same thing to the caller: not
        # measured.
        return None


def _strip_mpg_entries(post: list) -> list:
    """Return `post` with every mpg-matching entry removed at ENTRY
    granularity, not group granularity.

    A group whose `hooks` list mixes an mpg entry with an unrelated
    foreign entry (a hand-edited shape, or the legacy bare-`mpg` entry
    sharing a group with something else) must keep the foreign entry —
    dropping/replacing the whole group would silently destroy it. Only a
    group left with zero entries after stripping is dropped entirely;
    groups with no mpg entry at all are returned unchanged (identity, not
    a reconstructed copy), preserving any group-level custom keys and
    entry-level fields (`if`/`timeout`/`statusMessage`) verbatim.
    """
    kept = []
    for group in post:
        if not _group_has_mpg_entry(group):
            kept.append(group)
            continue
        foreign_entries = [e for e in group["hooks"] if not _is_mpg_entry(e)]
        if foreign_entries:
            kept.append({**group, "hooks": foreign_entries})
        # else: every entry in this group was mpg's own — drop the group.
    return kept


def merge_hook(settings: dict, python: str) -> dict:
    """Pure function: return a NEW dict with mpg's PostToolUse group present
    exactly once. Never mutates `settings`. All foreign content — other
    hook events, other PostToolUse groups, foreign entries co-located in
    the same group as an mpg entry, and sibling top-level keys — is
    preserved verbatim. Idempotent from ANY starting state, not just a
    canonical one: every mpg entry `_is_mpg_entry` recognizes is stripped
    before appending exactly one fresh group, so a settings file that
    somehow already has 2+ matching entries/groups converges to 1 on this
    call. A legacy mpg entry (any shape matching `_is_mpg_entry`) is
    migrated this same way, not duplicated.

    Raises HookConfigError if `hooks` or `hooks.PostToolUse` exist but are
    not the expected JSON type (fail-closed; caller must not write).
    """
    settings = copy.deepcopy(settings)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError("'hooks' is not a JSON object")
    post = hooks.setdefault(HOOK_EVENT, [])
    if not isinstance(post, list):
        raise HookConfigError(f"'hooks.{HOOK_EVENT}' is not a JSON array")

    kept = _strip_mpg_entries(post)
    kept.append(build_mpg_group(python))
    hooks[HOOK_EVENT] = kept
    return settings


def unmerge_hook(settings: dict) -> dict:
    """Pure function: return a NEW dict with mpg's hook entries removed at
    entry granularity (see `_strip_mpg_entries`). Prunes `hooks.PostToolUse`
    / `hooks` back to an empty structure only when nothing is left,
    restoring the exact pre-setup shape for the canonical case (symmetric
    with merge_hook). A no-op (returns settings unchanged) if mpg has no
    hook.
    """
    settings = copy.deepcopy(settings)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    post = hooks.get(HOOK_EVENT)
    if not isinstance(post, list):
        return settings
    remaining = _strip_mpg_entries(post)
    if remaining:
        hooks[HOOK_EVENT] = remaining
    else:
        hooks.pop(HOOK_EVENT, None)
    if not hooks:
        settings.pop("hooks", None)
    return settings


def is_ephemeral_interpreter(python: str) -> bool:
    """Best-effort detection of a one-shot `uvx`-style interpreter.

    Path ROOTS are anchored (`startswith`), cache markers are a bounded
    substring search — see the constants' docstrings for why the two use
    different matching strategies.
    """
    if any(python.startswith(root) for root in _EPHEMERAL_PATH_ROOTS):
        return True
    return any(marker in python for marker in _EPHEMERAL_CACHE_MARKERS)


def settings_local_path(project_root: Path) -> Path:
    return project_root / ".claude" / SETTINGS_FILE_NAME


def _resolved_target(path: Path) -> str:
    """Where `path` actually leads, or "unresolvable" if the walk got nowhere.

    Never raises, and never claims a target it did not resolve. `Path.resolve()`
    walks the filesystem, and how it reports an unresolvable link is version
    dependent: on a symlink loop Python <= 3.13 raises RuntimeError while 3.14
    returns the input path unchanged (measured on 3.12.12 and 3.14.6); a hostile
    or racing tree can raise OSError on any version. Both shapes mean the same
    thing here, and reporting "X is a symlink; mpg writes to X" would be a note
    that discloses nothing. Degrading beats taking down a run that would
    otherwise succeed.

    A dangling link is not unresolvable: it names a real destination that simply
    does not exist yet, which is exactly what the caller wants to know.

    The comparison is made against the absolute form. `resolve()` always
    absolutizes, so comparing it to a relative input can never match, and the
    3.14 "returned unchanged" shape would slip through as a note naming the
    link as its own destination — reachable in practice, since `--project-dir`
    is taken as a plain `Path` and may well be relative.
    """
    absolute = path.absolute()
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return "unresolvable"
    return "unresolvable" if resolved == absolute else str(resolved)


def symlinked_parent_notes(project_root: Path, write_paths: Iterable[Path]) -> list[str]:
    """Disclose every symlinked directory mpg is about to write through.

    For each path in `write_paths`, walk its components below `project_root` and
    report the OUTERMOST symlinked one, then de-duplicate across paths. Empty
    list when nothing on the way is a symlink — the overwhelmingly common case,
    where callers print nothing.

    Outermost-wins, then de-duplicated, is what makes the output match reality
    in both directions. A symlinked `.claude` is the first symlinked component
    of all three write paths, so it collapses to a single note: once writes
    leave for the link target, whether `skills` inside it is also a symlink is a
    fact about that other tree, not about where mpg's writes went. But when
    `.claude` is a real directory and `.claude/skills` and `.claude/rules` point
    at *different* places, there genuinely are two destinations and both are
    named — reporting only the first would make "mpg discloses where writes
    land" false (#192).

    Only the DIRECTORIES above each write target are inspected — neither
    `project_root` (the user named it, so a symlink there is theirs and already
    known to them) nor the final component. That last one is mpg's own artifact:
    the Skills and Rules entries are symlinks mpg itself creates, so walking
    into them would make a plain second `mpg setup` in an ordinary project
    announce mpg's own links back to the user.

    Callers pass the paths this run actually writes, rather than this module
    hardcoding them, so there is no second copy of the layout to drift from the
    real one — and no import cycle with `setup_cmd`, which owns those paths.

    `read_settings`/`write_settings_atomic` refuse a symlinked settings *file*;
    the directories above it are followed, not refused, because refusing would
    break the deliberate "config lives elsewhere" layouts that are the main
    reason to symlink into `.claude` at all. This discloses where a write went.
    It is not confinement of the tree (#170).
    """
    notes = []
    seen = set()
    for path in write_paths:
        try:
            relative = path.relative_to(project_root)
        except ValueError:
            continue
        current = project_root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                if current not in seen:
                    seen.add(current)
                    notes.append(
                        f"Note: {current} is a symlink; mpg writes to {_resolved_target(current)}"
                    )
                break
    return notes


def read_settings(path: Path) -> dict:
    """Read and parse a settings file. An absent file reads as `{}`.

    Fail-closed: symlinks (including dangling ones), unreadable files,
    invalid JSON, and non-object JSON all raise HookConfigError rather
    than guessing — the caller must leave the file untouched.
    """
    if path.is_symlink():
        msg = f"{path} is a symlink; refusing to follow into it"
        raise HookConfigError(msg)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        msg = f"cannot read {path}: {e}"
        raise HookConfigError(msg) from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        msg = f"{path} is not valid JSON: {e}"
        raise HookConfigError(msg) from e
    if not isinstance(data, dict):
        msg = f"{path} does not contain a JSON object"
        raise HookConfigError(msg)
    return data


def write_settings_atomic(path: Path, settings: dict) -> None:
    """Atomic write: a temp file in the same directory, then `os.replace`.
    A crash or concurrent read mid-write always sees either the old file or
    the new one in full, never a partial write.

    Preserves the pre-existing file's permission bits: `tempfile.mkstemp`
    creates the temp file at 0600, and `os.replace` keeps the *new* file's
    mode — without re-applying the original, every write would silently
    narrow a pre-existing file's permissions (e.g. a user's own 0644) to
    0600 on each `mpg setup` re-run.
    """
    if path.is_symlink():
        msg = f"{path} is a symlink; refusing to follow into it"
        raise HookConfigError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode = path.stat().st_mode if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".mpg-settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        if original_mode is not None:
            os.chmod(tmp_name, stat.S_IMODE(original_mode))
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def remove_hook(*, project_root: Path, dry_run: bool = False) -> bool:
    """Remove mpg's PostToolUse hook from ``<project_root>/.claude/settings.local.json``.

    Idempotent: a no-op success if mpg has no hook registered. Shared by
    ``setup --no-hook`` (opt-out = remove, not merely skip) and
    ``uninstall`` (symmetry with setup_hook) — kept in this module rather
    than either caller's to avoid a setup_cmd/uninstall_cmd import cycle.
    """
    path = settings_local_path(project_root)

    try:
        settings = read_settings(path)
    except HookConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

    if not has_mpg_hook(settings):
        print(f"Hook not registered at {path} — nothing to remove.")
        return True

    if dry_run:
        print(f"Would remove mpg hook from {path}")
        return True

    unmerged = unmerge_hook(settings)
    try:
        write_settings_atomic(path, unmerged)
    except HookConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Error: failed to write {path}: {e}", file=sys.stderr)
        return False

    print(f"Hook removed from {path}")
    return True
