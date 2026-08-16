"""Read-only report on the four delivery channels `mpg setup` writes.

`setup` writes state into a project — two symlinks, a hook registration, an MCP
registration — and that state decays independently of the package. Every way it
decays is silent: a symlink flattened into a real file still has content, a link
whose target moved still resolves as a name, an unregistered hook simply never
fires, and an MCP entry pinned to a since-replaced interpreter keeps sitting in
the config. Nothing raises, so the only visible symptom is that guidance stops
arriving — with no signal pointing at the cause.

This module reports; it never writes. `setup` stays the repair tool. The states
below separate "installed and working" from "not installed" from "installed and
broken", because `setup` has `--mcp-only` / `--skills-only` / `--no-hook`: a
channel that is absent may be exactly what the user chose, and calling that a
failure would make a red result meaningless.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from modern_python_guidance.hook_config import (
    HOOK_SUBCOMMAND,
    HookConfigError,
    _is_mpg_entry,
    find_mpg_group,
    is_ephemeral_interpreter,
    read_settings,
    settings_local_path,
)
from modern_python_guidance.setup_cmd import (
    LINK_ABSENT,
    LINK_FLATTENED,
    LINK_LINKED,
    LINK_STALE,
    MCP_SERVER_NAME,
    _find_project_root,
    _find_rule_source,
    _find_skills_dir,
    _resolve_cwd,
    _rules_file_path,
    _run_claude_mcp_quiet,
    _skills_link_path,
    link_state,
)

CHANNEL_MCP = "mcp"
CHANNEL_SKILLS = "skills"
CHANNEL_RULES = "rules"
CHANNEL_HOOK = "hook"

PRESENT = "present"
"""Installed and working."""

DEGRADED = "degraded"
"""Installed but broken. The only state that makes `doctor` exit 1."""

ABSENT = "absent"
"""Not installed. `setup`'s own flags make this a legitimate configuration."""

UNKNOWN = "unknown"
"""Could not be determined. Never folded into `present` — a check that cannot
distinguish "healthy" from "not measured" is not a check."""


@dataclass(frozen=True, slots=True)
class ChannelReport:
    """One channel's verdict, plus what to do about it."""

    channel: str
    state: str
    detail: str
    fix: str = ""


def _link_report(channel: str, link_path: Path, source: Path, what: str) -> ChannelReport:
    """Turn `link_state` into a report. Shared by the skills and rules channels,
    which differ only in wording.

    The classification comes from the same predicate `setup` uses, but the two
    read it differently, and that difference is the point. `setup` asks "is the
    link I am about to write already here?", so a link to anywhere else has to
    be replaced. `doctor` asks "is the link working?", and a link into a
    *different* mpg installation is working fine — the user installed mpg with
    uv and is running `doctor` out of a source checkout, say.

    Judging `stale` as broken would make the verdict depend on which
    interpreter invoked `doctor`, reporting healthy links as degraded from
    `uvx` or a second venv. Measured, not predicted: the first run of this
    command against an already-repaired workspace called both links degraded.
    So a stale link is degraded only when it leads nowhere — `exists()` follows
    the link, so it answers exactly that.
    """
    state = link_state(link_path, source)
    if state == LINK_LINKED:
        return ChannelReport(channel, PRESENT, f"linked to {source}")
    if state == LINK_FLATTENED:
        return ChannelReport(
            channel,
            DEGRADED,
            f"{link_path} is not a symlink — a real {what} occupies the path, so its"
            " content is frozen at whatever was copied there",
            "Remove it and re-run `mpg setup` (setup refuses to overwrite it for you)",
        )
    if state == LINK_STALE:
        target = link_path.readlink()
        if not link_path.exists():
            return ChannelReport(
                channel,
                DEGRADED,
                f"{link_path} points at {target}, which does not exist",
                "Run `mpg setup` to re-point it",
            )
        # Existing is not enough to call it another mpg installation. Both
        # delivery paths end in a fixed name (`modern-python-guidance`,
        # `modern-python.md`) in every layout mpg ships, so comparing the final
        # component separates "another install of this tool" from "a link that
        # was repointed at something else entirely" — the second being one of
        # the decays named at the top of this module, which the earlier version
        # of this branch reported as healthy while asserting an installation it
        # had never looked for.
        try:
            leads_to_an_mpg_asset = link_path.resolve().name == source.name
        except (OSError, RuntimeError):
            leads_to_an_mpg_asset = False
        if leads_to_an_mpg_asset:
            return ChannelReport(
                channel,
                PRESENT,
                f"linked to {target} — a different mpg installation than the one"
                f" running doctor ({source}), which is fine as long as you meant it",
            )
        return ChannelReport(
            channel,
            DEGRADED,
            f"{link_path} points at {target}, which is not an mpg {what}",
            "Run `mpg setup` to re-point it",
        )
    if state == LINK_ABSENT:
        return ChannelReport(channel, ABSENT, f"no {what} at {link_path}", "Run `mpg setup`")
    # Every state `link_state` returns is named above. Falling through to a
    # default of "absent" would let a fifth state be reported as "nothing is
    # installed" — the same shape as a command listed in the parser with no
    # dispatch behind it, which this codebase already answers with an error
    # rather than a silent success.
    msg = f"unhandled link state: {state!r}"
    raise AssertionError(msg)


def diagnose_skills(project_dir: Path | None = None) -> ChannelReport:
    try:
        source = _find_skills_dir()
    except FileNotFoundError as e:
        return ChannelReport(CHANNEL_SKILLS, UNKNOWN, f"cannot locate the bundled skills: {e}")
    return _link_report(CHANNEL_SKILLS, _skills_link_path(project_dir), source, "directory")


def diagnose_rules(project_dir: Path | None = None) -> ChannelReport:
    try:
        source = _find_rule_source()
    except FileNotFoundError as e:
        return ChannelReport(CHANNEL_RULES, UNKNOWN, f"cannot locate the bundled rule: {e}")
    return _link_report(CHANNEL_RULES, _rules_file_path(project_dir), source, "file")


def diagnose_hook(project_dir: Path | None = None) -> ChannelReport:
    """Report the PostToolUse hook registration.

    A `HookConfigError` is `degraded`, not `unknown`: the settings file is there
    and mpg cannot read it, which is a broken state a user can act on — the four
    shapes `read_settings` rejects (a symlinked file, an unreadable one, invalid
    JSON, a non-object) are all things that went wrong, not things that could
    not be measured. An absent file is not an error at all; `read_settings`
    returns `{}` for it and the hook reads as `absent`.
    """
    root = project_dir or _find_project_root()
    path = settings_local_path(root)
    try:
        settings = read_settings(path)
    except HookConfigError as e:
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"cannot read {path}: {e}",
            "Fix or remove that file, then run `mpg setup --with-hook`",
        )

    group = find_mpg_group(settings)
    if group is None:
        return ChannelReport(
            CHANNEL_HOOK,
            ABSENT,
            f"no mpg PostToolUse hook in {path}",
            "Run `mpg setup --with-hook`",
        )

    # mpg's own entry, not merely the first one in the group. `find_mpg_group`
    # returns the group *containing* an mpg entry, and `_strip_mpg_entries`
    # exists precisely because a group may mix mpg's entry with a foreign
    # tool's — taking the first entry would have doctor judging somebody
    # else's hook and reporting its binary as mpg's.
    entry = next((e for e in group.get("hooks", []) if _is_mpg_entry(e)), None)
    command = entry.get("command", "") if entry else ""
    if not isinstance(command, str) or not command:
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the mpg hook group in {path} has no usable command",
            "Run `mpg setup --with-hook` to rewrite it",
        )

    # The legacy registration README used to document puts the whole invocation
    # in `command` as a shell string (`mpg hook claude-post-tool-use`), and
    # `_is_mpg_entry` still recognises it. Everything below treats `command` as
    # an interpreter path, which that form is not: `Path(...).exists()` would
    # say "does not exist" about a string that may well resolve on PATH, and
    # `is_ephemeral_interpreter`'s anchored prefixes never match it. Since
    # doctor's whole population is old and drifted installs, this form is
    # exactly what it will meet.
    if HOOK_SUBCOMMAND in command.split():
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook is registered in the legacy shell-string form ({command}), which"
            " depends on PATH — Claude Code spawns hooks from its own environment, where"
            " a venv-only interpreter is not on PATH",
            "Run `mpg setup --with-hook` to pin an absolute interpreter path",
        )

    # `is_ephemeral_interpreter` is applied to the *registered* command, not to
    # `sys.executable` the way setup applies it: setup asks "would pinning this
    # interpreter be a mistake", doctor asks "was that mistake already made".
    # Both are handed a bare path, which is the shape the function's anchored
    # prefix matching assumes — hence the legacy form being answered above.
    if is_ephemeral_interpreter(command):
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook is pinned to a throwaway interpreter ({command})",
            "Re-run `mpg setup --with-hook` from a durable installation",
        )
    if not Path(command).exists():
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {command}, which does not exist",
            "Run `mpg setup --with-hook` to re-point it",
        )
    return ChannelReport(CHANNEL_HOOK, PRESENT, f"registered in {path}, running {command}")


def _parse_mcp_fields(stdout: bytes) -> dict[str, str]:
    """The `Key: Value` lines of `claude mcp get` output, first occurrence wins.

    Deliberately tolerant about lines it does not recognise — the header (`mpg:`)
    and the trailing hint (`To remove this server, run: ...`) both parse into
    harmless entries. What matters is that a missing `Status` stays missing
    rather than being invented, so a changed output format reads as `unknown`.
    """
    fields: dict[str, str] = {}
    for line in stdout.decode(errors="replace").splitlines():
        key, sep, value = line.strip().partition(":")
        if not sep:
            continue
        key = key.strip()
        if key:
            fields.setdefault(key, value.strip())
    return fields


def diagnose_mcp(project_dir: Path | None = None) -> ChannelReport:
    """Report the MCP registration by asking `claude` whether it connects.

    Reading `Status:` rather than comparing the registered `Command:` against
    this process's own installation. The comparison would describe *whichever
    interpreter ran doctor* — run it via `uvx`, or from a second venv, and a
    perfectly healthy registration reads as broken. Connecting is a property of
    the registration itself, so the answer does not depend on who asks.

    `claude mcp get` starts the server to answer (measured: 1.5s versus 0.05s
    for `claude --version`). That cost is the reason `claude mcp list` is not
    used — it connects to every configured server and took 30s here.

    A missing `claude` is `absent`, not `unknown`: `setup_mcp` refuses to
    register anything without it (`setup_cmd.py`), so "no claude" implies "no
    mpg registration". Calling it `unknown` would make exit 0 unreachable in CI,
    where `claude` is not installed.
    """
    claude = shutil.which("claude")
    if claude is None:
        return ChannelReport(
            CHANNEL_MCP,
            ABSENT,
            "'claude' is not on PATH, so there is no MCP registration",
            "Install Claude Code, then run `mpg setup`",
        )

    result = _run_claude_mcp_quiet(
        [claude, "mcp", "get", MCP_SERVER_NAME], cwd=_resolve_cwd(project_dir)
    )
    if result is None:
        return ChannelReport(
            CHANNEL_MCP,
            UNKNOWN,
            "`claude mcp get` did not complete (timed out, or could not be run)",
        )
    if result.returncode != 0:
        # Asking about an unregistered server exits non-zero and says so. So
        # does a corrupt config, a failed authorisation, and a crash. Reading
        # "not registered" out of every non-zero exit would report absence —
        # and, since absence is healthy, exit 0 — for a machine whose
        # registration could not be examined at all. Recognising the one
        # message that means absence, and treating everything else as
        # unmeasured, keeps this channel from contradicting the rest of the
        # command. If the wording changes, this falls to `unknown`, which is
        # the safe direction: it says "look" rather than "all clear".
        stderr = (result.stderr or b"").decode(errors="replace").strip()
        if "No MCP server named" in stderr:
            return ChannelReport(
                CHANNEL_MCP,
                ABSENT,
                f"no MCP server named {MCP_SERVER_NAME!r} is registered",
                "Run `mpg setup`",
            )
        return ChannelReport(
            CHANNEL_MCP,
            UNKNOWN,
            f"`claude mcp get` exited {result.returncode}: {stderr or 'no error output'}",
        )

    fields = _parse_mcp_fields(result.stdout)
    status = fields.get("Status")
    if status is None:
        return ChannelReport(
            CHANNEL_MCP,
            UNKNOWN,
            "`claude mcp get` succeeded but its output carried no Status line",
        )

    # Reported, never compared: which command is registered is useful to see and
    # misleading to judge, for the reason in this function's docstring.
    where = f" [{fields['Scope']}]" if "Scope" in fields else ""
    registered = f" running {fields['Command']}" if "Command" in fields else ""
    if "Connected" not in status:
        return ChannelReport(
            CHANNEL_MCP,
            DEGRADED,
            f"registered{where}{registered} but not connected — Status: {status}",
            "Run `mpg setup` to re-register against the current installation",
        )
    return ChannelReport(CHANNEL_MCP, PRESENT, f"connected{where}{registered}")


_DIAGNOSERS = {
    CHANNEL_MCP: diagnose_mcp,
    CHANNEL_SKILLS: diagnose_skills,
    CHANNEL_RULES: diagnose_rules,
    CHANNEL_HOOK: diagnose_hook,
}

CHANNELS: tuple[str, ...] = tuple(_DIAGNOSERS)
"""Every channel `setup` writes, derived from the table that diagnoses them.

Written out separately at first, which meant two lists of the same four names:
a channel present in one and missing from the other is either a `KeyError` or a
silently unreported channel, depending on which way they drifted. Derived, the
question cannot be asked."""


def diagnose_all(project_dir: Path | None = None) -> list[ChannelReport]:
    """One report per entry in `CHANNELS`, in that order."""
    return [_DIAGNOSERS[name](project_dir) for name in CHANNELS]


def summarize(reports: list[ChannelReport]) -> int:
    """The exit status for a set of reports.

    Empty input is 2, not 0. A run that evaluated nothing has not established
    that anything is healthy, and returning 0 for it would make "everything is
    fine" indistinguishable from "nothing was measured" — the failure this
    command exists to catch, committed by the command itself.
    """
    if not reports:
        return 2
    states = {report.state for report in reports}
    if UNKNOWN in states:
        return 2
    if DEGRADED in states:
        return 1
    return 0
