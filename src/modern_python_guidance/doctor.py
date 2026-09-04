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

import contextlib
import errno
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from modern_python_guidance.hook_config import (
    HOOK_SUBCOMMAND,
    HOOK_TOOLS,
    HookConfigError,
    build_mpg_hook_entry,
    find_mpg_entries,
    is_ephemeral_interpreter,
    matcher_fires_on,
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
    _first_byte_readable,
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


_SEVERITY = {PRESENT: 0, ABSENT: 0, DEGRADED: 1, UNKNOWN: 2}
"""How states rank, and what each rank exits with.

One table, read twice: folding several observations of one channel into a
verdict, and folding several channels into the process's exit status. Those are
the same ordering — `unknown` outranks `degraded` because "could not be
measured" must not be reported as a measured failure, and neither may be
flattened into health — and writing it twice would be two places to change with
only one of them read on any given day."""


@dataclass(frozen=True, slots=True)
class ChannelReport:
    """One channel's verdict, plus what to do about it."""

    channel: str
    state: str
    detail: str
    fix: str = ""


def _worst(reports: list[ChannelReport]) -> ChannelReport:
    """The report that decides the channel. Ties keep the first, so the order
    the observations were made in is the order the reader sees them explained."""
    return max(reports, key=lambda report: _SEVERITY[report.state])


def _skills_are_delivered(link_path: Path) -> bool:
    """A skills directory that would actually deliver something.

    Applied through the link, not to the resolved target, because what matters
    is what a reader following this path sees. The bundled layout puts
    `SKILL.md` at the top of the directory, and it is what Claude Code loads.
    """
    return link_path.is_dir() and _first_byte_readable(link_path / "SKILL.md")


def _rule_is_delivered(link_path: Path) -> bool:
    return link_path.is_file() and _first_byte_readable(link_path)


def _link_target(link_path: Path) -> str:
    """A symlink's recorded destination, for wording only.

    `link_state` has already classified the link by the time this runs, so this
    is a second read of a path the first one no longer owns. A read-only
    diagnostic that tracebacks because the tree moved under it has failed at
    the one job it has, so a failure here degrades to a phrase.
    """
    try:
        return str(link_path.readlink())
    except OSError:
        return "a destination that could no longer be read"


def _link_report(
    channel: str,
    link_path: Path,
    source: Path,
    what: str,
    delivers: Callable[[Path], bool],
) -> ChannelReport:
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

    `delivers` guards **both** paths to `present`. Neither of them used to look
    at the target: one trusted the bundled source, which is accepted on
    `is_dir()` / `is_file()` alone, and the other compared the final path
    component and then told the reader it had found "a different mpg
    installation". An empty directory carrying the right name satisfied that,
    which is the decay this module's own docstring opens by naming — a link
    whose target moved still resolves as a name.
    """
    state = link_state(link_path, source)
    if state == LINK_LINKED:
        if not delivers(link_path):
            return ChannelReport(
                channel,
                DEGRADED,
                f"{link_path} is linked to {source}, which holds no readable {what}"
                " content — the link is right and there is nothing behind it",
                "Reinstall mpg, then run `mpg setup`",
            )
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
        target = _link_target(link_path)
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
            if not delivers(link_path):
                return ChannelReport(
                    channel,
                    DEGRADED,
                    f"{link_path} points at {target}, which carries an mpg {what}'s name"
                    " and no readable content behind it",
                    "Run `mpg setup` to re-point it at this installation",
                )
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
    return _link_report(
        CHANNEL_SKILLS,
        _skills_link_path(project_dir),
        source,
        "directory",
        _skills_are_delivered,
    )


def diagnose_rules(project_dir: Path | None = None) -> ChannelReport:
    try:
        source = _find_rule_source()
    except FileNotFoundError as e:
        return ChannelReport(CHANNEL_RULES, UNKNOWN, f"cannot locate the bundled rule: {e}")
    return _link_report(
        CHANNEL_RULES,
        _rules_file_path(project_dir),
        source,
        "file",
        _rule_is_delivered,
    )


def _entry_shape_report(entry: dict, path: Path) -> ChannelReport:
    """One mpg entry, judged on its written shape alone.

    Nothing here runs the registered command. `command` is an arbitrary string
    out of a settings file — it need not be a Python interpreter, and a binary
    is free to ignore whatever arguments it is handed — so executing it to find
    out whether the hook works would turn a read-only diagnostic into a way to
    run anything a settings file names. What can be established without that:
    the entry is the shape Claude Code will run, and the shape mpg writes.
    """
    command = entry.get("command", "")
    if not isinstance(command, str) or not command:
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"an mpg hook entry in {path} has no usable command",
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

    entry_type = entry.get("type")
    if entry_type != "command":
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the mpg hook entry in {path} has type {entry_type!r}, so Claude Code will"
            " not run it as a command",
            "Run `mpg setup --with-hook` to rewrite it",
        )

    # Compared against the canonical shape rather than merely looked for. The
    # identity check that found this entry (`_is_mpg_entry`) is satisfied by the
    # subcommand token appearing anywhere in `args`, which is the right test for
    # "is this ours" and no test at all for "will this invoke us".
    expected_args = build_mpg_hook_entry(command)["args"]
    if entry.get("args") != expected_args:
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the mpg hook entry in {path} runs {entry.get('args')!r}, not {expected_args!r}",
            "Run `mpg setup --with-hook` to rewrite it",
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
    # Existing is not the same as being runnable, and this channel now claims
    # the latter. `Path("/")` exists; so does a text file with no execute bit.
    # Claude Code can spawn neither, so reporting either as `present` would
    # state exactly the thing this change was written to stop.
    interpreter = Path(command)
    if not interpreter.exists():
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {command}, which does not exist",
            "Run `mpg setup --with-hook` to re-point it",
        )
    if not interpreter.is_file():
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {command}, which is not a file",
            "Run `mpg setup --with-hook` to re-point it",
        )
    if not os.access(interpreter, os.X_OK):
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {command}, which is not executable",
            "Run `mpg setup --with-hook` to re-point it",
        )
    return ChannelReport(CHANNEL_HOOK, PRESENT, f"registered in {path}, running {command}")


def _tool_coverage_reports(found: list[tuple[dict, dict]], path: Path) -> list[ChannelReport]:
    """One report per tool mpg means to hook, counting the entries that select it.

    Counted per tool rather than per group. Two groups is not the same as two
    registrations: `matcher: "Edit"` beside `matcher: "Write"` is two groups
    covering one tool each, which is what mpg's own matcher covers in one — and
    a single group whose `hooks` list holds two mpg entries is one group holding
    two registrations. Counting groups gets both of those backwards.

    The report for a duplicate says how many entries are registered, and stops
    there. Claude Code's documented de-duplication covers the same handler
    appearing in more than one settings file; what it does with a repeat inside
    one file is not something this can claim to know.
    """
    reports: list[ChannelReport] = []
    for tool in HOOK_TOOLS:
        verdicts = [matcher_fires_on(group.get("matcher"), tool) for group, _ in found]
        unevaluated = sum(verdict is None for verdict in verdicts)
        firing = sum(verdict is True for verdict in verdicts)
        # An entry nobody could evaluate does not erase what the others
        # established. Two canonical entries are already a duplicate whatever a
        # third turns out to be, and the duplicate carries a fix while
        # "not established" carries none. Only the counts that a further
        # matcher could still change are reported as unmeasured.
        #
        # `fix` stays empty on purpose — there is nothing to repair when the
        # measurement is what failed, and offering one would assert a diagnosis
        # this branch does not have. The sentence about `--with-hook` is in the
        # detail instead, and is worded as what that command does rather than as
        # advice: a matcher outside the portable subset may be doing exactly
        # what its author intended, and this branch cannot tell that case from a
        # registration that never fires. Without it the reader is told a hook
        # may not be reaching them and given no way forward at all, which is
        # what a working-but-unevaluable matcher used to get as `degraded` with
        # a fix attached.
        if unevaluated and firing < 2:
            reports.append(
                ChannelReport(
                    CHANNEL_HOOK,
                    UNKNOWN,
                    f"a matcher this cannot evaluate appears on {unevaluated} of the"
                    f" {len(found)} mpg hook entries in {path}, so the number reaching"
                    f" {tool} was not established (at least {firing})."
                    " `mpg setup --with-hook` would replace it with mpg's own matcher,"
                    " which this can evaluate",
                )
            )
            continue
        if firing == 0:
            reports.append(
                ChannelReport(
                    CHANNEL_HOOK,
                    DEGRADED,
                    f"the hook is registered in {path}, but no entry's matcher selects"
                    f" {tool}, so editing a file never reaches it",
                    "Run `mpg setup --with-hook` to register mpg's own matcher",
                )
            )
        elif firing > 1:
            reports.append(
                ChannelReport(
                    CHANNEL_HOOK,
                    DEGRADED,
                    f"{firing} mpg hook entries in {path} select {tool}; setup writes exactly one",
                    "Run `mpg setup --with-hook` to converge them into one",
                )
            )
    return reports


def diagnose_hook(
    project_dir: Path | None = None, *, run_interpreter: bool = False
) -> ChannelReport:
    """Report the PostToolUse hook registration.

    `run_interpreter` defaults to False, and that default is the security
    boundary rather than a convenience: turning it on executes a string out of a
    settings file, which may have arrived with a repository someone cloned. See
    `_probe_interpreter` for what the execution is bounded by, and what it is
    not.

    A `HookConfigError` is `degraded`, not `unknown`: the settings file is there
    and mpg cannot read it, which is a broken state a user can act on — the four
    shapes `read_settings` rejects (a symlinked file, an unreadable one, invalid
    JSON, a non-object) are all things that went wrong, not things that could
    not be measured. An absent file is not an error at all; `read_settings`
    returns `{}` for it and the hook reads as `absent`.

    Every mpg entry is examined, not the first one found. The writing side has
    always allowed for more than one — `merge_hook` converges "from ANY starting
    state" — so a reader that stops at the first can call the channel healthy
    with a second, broken registration sitting behind it.
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

    found = find_mpg_entries(settings)
    if not found:
        return ChannelReport(
            CHANNEL_HOOK,
            ABSENT,
            f"no mpg PostToolUse hook in {path}",
            "Run `mpg setup --with-hook`",
        )

    shape_reports = [_entry_shape_report(entry, path) for _, entry in found]
    probe_reports = _probe_reports(found, shape_reports, path) if run_interpreter else []
    reports = [*shape_reports, *probe_reports, *_tool_coverage_reports(found, path)]
    worst = _worst(reports)
    if worst.state != PRESENT:
        return worst
    if len(found) == 1:
        return _with_probe_note(worst, probe_reports)
    commands = ", ".join(sorted({entry.get("command", "") for _, entry in found}))
    return _with_probe_note(
        ChannelReport(
            CHANNEL_HOOK,
            PRESENT,
            f"registered in {path} as {len(found)} entries, running {commands}",
        ),
        probe_reports,
    )


def _with_probe_note(report: ChannelReport, probe_reports: list[ChannelReport]) -> ChannelReport:
    """Fold what the probe established into a `present` verdict.

    Without this the probe is invisible when it succeeds: `_worst` keeps the
    first report of the winning severity, which is the shape check, so someone
    who passed `--run-interpreter` would read the same line as someone who did
    not. Asking a command to do more work and showing no sign of it is how a
    flag gets assumed broken.
    """
    if not probe_reports:
        return report
    if len(probe_reports) == 1:
        note = probe_reports[0].detail
    else:
        # Four probe details concatenated is a line nobody reads, and each one
        # repeats the interpreter path the shape report already carries. The
        # count is what a reader needs; the paths are above it.
        note = f"{len(probe_reports)} interpreters each loaded mpg"
    return ChannelReport(report.channel, report.state, f"{report.detail} — {note}", report.fix)


PROBE_TIMEOUT_SECONDS = 5.0
"""How long a probed interpreter gets before it is killed.

Measured against 0.08-0.18s for a healthy `-m modern_python_guidance --version`
on the machine this was written on — warm, with `__pycache__` populated. A cold
first run, or a network filesystem, is slower by some multiple nobody here has
measured, and the cost of guessing low is a `degraded`-looking exit 2 rather
than a wrong answer.
"""

PROBE_LIMIT = 4
"""How many distinct interpreters get probed in one run.

Commands are de-duplicated first, so this only bites on a settings file naming
several different interpreters. Without it the ceiling is the number of entries
times the timeout, which a file with twenty entries turns into a minute and a
half of a command someone expects to answer immediately.
"""


_PROBE_ENV = {
    key: value
    for key, value in ((name, os.environ.get(name)) for name in ("PATH", "HOME"))
    if value is not None
}
"""The environment a probe runs with: two variables, neither of them a secret.

An empty environment was the first attempt, and it is stricter than the thing
being measured. Claude Code spawns the hook with the user's environment, and a
`command` that is a wrapper — a pyenv or conda shim is a shell script reading
`PATH` and `HOME` — cannot start without them. The probe would report an
interpreter the hook loads fine as broken, and the installations `doctor` exists
for are exactly the drifted ones most likely to be reached through a shim.

Everything else is dropped, which is what keeps a caller's `PYTHONPATH` from
answering in the interpreter's place, and keeps credentials held in the
environment away from a command a settings file named. It does nothing about
credentials in files; see `_probe_interpreter`.
"""

PROBE_OUTPUT_LIMIT = 4096
"""How much of the child's stdout is read before it is cut off.

A healthy answer is about thirty bytes. Reading without a limit is not a
theoretical problem: `cat /dev/zero` as the registered command took this
process to 2.3 GB of resident memory in one second, measured — five seconds is
ten times that, and a laptop swaps or dies. The output beyond this is not
needed to recognise a version string.
"""

PROBE_PROG = "modern-python-guidance"
"""The `prog` argparse prints, from `cli.build_parser`. Pinned by a test that
runs the real `--version`: a probe matching against a string the CLI stopped
printing would call every healthy installation broken."""

_VERSION_TOKEN = re.compile(r"[0-9][0-9A-Za-z.+_-]{0,63}")
"""What may follow the program name and still count as a version.

Narrow because this string is printed back to a terminal. The probe's output
comes from a command a settings file names, and "any token without spaces" let
`modern-python-guidance 1.1.0\\x1b[2K\\rhook\\tpresent\\t...` through — the escape
erases the line and redraws it, so the child writes doctor's own verdict.
Measured with a two-line shell script. A version is digits, letters, and the
punctuation PEP 440 and SemVer use; anything else is not one.
"""


def _probe_command(command: str) -> list[str]:
    """The argv a probe runs.

    Deliberately the same shape Claude Code spawns (`hook_config`'s
    `build_mpg_hook_entry`), with `--version` in place of the hook subcommand.
    An earlier draft added `-I`, reasoning that isolation answers "is mpg in
    *this* interpreter". It answers a stricter question than the hook asks:
    `-I` also drops user site-packages, which the hook does not, so a
    `pip install --user` installation the hook loads fine reported as broken —
    measured. The environment is cut down at the call site to `PATH` and `HOME`
    (see `_PROBE_ENV`), which is what keeps a caller's `PYTHONPATH` from
    answering in the interpreter's place.
    """
    return [command, "-m", "modern_python_guidance", "--version"]


def _version_from_probe_output(printed: str) -> str | None:
    """The version a probe reported, or None if it did not report one.

    Matches the program name and accepts whatever version follows, rather than
    comparing against this process's `__version__`. Pinning the exact version
    would make `doctor` answer about *its own* installation: a hook wired to an
    interpreter holding an older mpg loads perfectly well, and an equality test
    calls it "not an interpreter with mpg installed" — which is false, and is
    the same mistake `_link_report` avoids for a link into another installation
    and `diagnose_mcp` avoids by reading `Status:` instead of comparing paths.
    """
    prefix = f"{PROBE_PROG} "
    if not printed.startswith(prefix):
        return None
    version = printed[len(prefix) :].strip()
    return version if _VERSION_TOKEN.fullmatch(version) else None


@dataclass(frozen=True, slots=True)
class _ProbeOutput:
    """What reading a probe's stdout produced, and how the reading ended."""

    data: bytes
    timed_out: bool
    hit_limit: bool


def _read_bounded(proc: subprocess.Popen[bytes]) -> _ProbeOutput:
    """Read at most `PROBE_OUTPUT_LIMIT` bytes, for at most the timeout.

    Written by hand because both `subprocess.run(timeout=…)` and
    `communicate(timeout=…)` read until EOF, which bounds neither memory nor —
    as it turned out — time.

    The time bound is the sharp edge. `communicate` after a timeout waits for
    EOF on the pipe, and EOF does not arrive while *any* process holds the write
    end. A child that calls `setsid()` and leaves a grandchild holding stdout
    survives `killpg`, and the second `communicate` then blocks forever: `mpg
    doctor --run-interpreter` never returns, with no message. Measured against
    exactly that script, which is why the pipe is read with a deadline and
    closed rather than drained.

    **One exit, on purpose.** An earlier version returned directly when the
    deadline passed, which jumped over the kill below it — the command came back
    on time and left the child running, exactly the case the timeout exists for.
    A `finally` restores file descriptors; it does not run code written after
    the block it guards. So the loop sets a flag and every path leaves through
    the same tail.
    """
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    chunks: list[bytes] = []
    size = 0
    timed_out = False
    hit_limit = False
    stream = proc.stdout
    assert stream is not None, "the probe always opens stdout as a pipe"
    try:
        selector = selectors.DefaultSelector()
        try:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            while size < PROBE_OUTPUT_LIMIT:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                if not selector.select(timeout=remaining):
                    continue
                chunk = stream.read(PROBE_OUTPUT_LIMIT - size)
                if chunk is None:
                    # Non-blocking read with nothing available yet.
                    continue
                if not chunk:
                    break  # EOF: the child closed stdout.
                chunks.append(chunk)
                size += len(chunk)
            else:
                # Left by the loop condition rather than a `break`: the limit is
                # what stopped the reading, so the child may still be talking.
                hit_limit = True
        finally:
            # `register` can raise, and then `close` has to happen anyway or the
            # kqueue/epoll descriptor leaks.
            selector.close()
    finally:
        # Closing the read end means a child still writing gets EPIPE rather
        # than this process waiting on it.
        with contextlib.suppress(OSError):
            stream.close()

    if not timed_out:
        # Give the child the rest of the window to exit so `returncode` is real.
        # `wait` is bounded; nothing here waits on the pipe.
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
    if timed_out:
        _kill_process_group(proc)
        proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=1.0)
    return _ProbeOutput(b"".join(chunks), timed_out, hit_limit)


def _probe_interpreter(command: str, shown: str | None = None) -> ChannelReport:
    """Run the registered interpreter and see whether mpg answers.

    This is the one thing in `doctor` that executes something a settings file
    names, and it runs only when asked for by `--run-interpreter`. Everything
    below is about bounding what that costs, because `command` is an arbitrary
    string: it need not be a Python interpreter, and a binary is free to ignore
    the arguments it is handed.

    **Exit status is not the test.** A program that ignores its arguments and
    exits 0 satisfies one, and the shape checks above cannot tell it from a real
    interpreter — measured, with a two-line shell script. So the verdict is the
    *output*: `present` requires a line naming mpg and a version.

    That is why stdout is a pipe rather than `DEVNULL`, and why `_read_bounded`
    exists instead of `communicate`: reading to EOF bounds neither the memory a
    chatty child costs nor the time a child that escapes the process group can
    take. Both were measured, and both are described there.

    `Popen` by hand rather than `subprocess.run(timeout=...)`: that helper kills
    the direct child only, so a process which forked before the timeout keeps
    running, detached from anything that could report it. `start_new_session`
    puts the child in its own process group and the timeout path kills the
    group.

    **What is not bounded**: the child runs as the user, so it can reach the
    network, read anything they can read, and — the more durable problem —
    *write* anything they can write, five seconds being ample for appending to
    a shell profile. A `setsid()` of its own outlives the group kill and keeps
    running after `doctor` has answered. Cutting the environment down to `PATH`
    and `HOME` keeps secrets held *in the environment* out of reach; it does
    nothing about `~/.aws/credentials`. Opting in is the actual control.

    `shown` is what the reader is told was run, and defaults to what was
    actually run. They differ for a relative `command`, which is executed as an
    absolute path (see `_probe_reports`) but named in the settings file the
    short way: printing both puts one entry on screen under two names, looking
    like two interpreters.
    """
    shown = shown if shown is not None else command
    with tempfile.TemporaryDirectory() as sandbox:
        # cwd is a directory this process just made and nothing has written to.
        # Run it in the project instead and a `modern_python_guidance.py` lying
        # there is imported in preference to the installed package, which is a
        # `present` verdict for an interpreter that has nothing installed.
        try:
            proc = subprocess.Popen(
                _probe_command(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=sandbox,
                env=_PROBE_ENV,
                start_new_session=True,
            )
        except OSError as exc:
            return _probe_start_failure(shown, exc)
        output = _read_bounded(proc)
        if output.timed_out:
            return ChannelReport(
                CHANNEL_HOOK,
                UNKNOWN,
                f"the hook's interpreter {command} did not answer within"
                f" {PROBE_TIMEOUT_SECONDS:g}s, so whether it can load mpg was not established",
            )
    printed = output.data.decode(errors="replace").strip()
    version = _version_from_probe_output(printed)
    if proc.returncode == 0 and version is not None:
        return ChannelReport(CHANNEL_HOOK, PRESENT, f"{shown} loaded mpg {version}")
    if output.hit_limit:
        # The exit status is not the child's own here: closing the pipe at the
        # limit is what ended it, and reporting the SIGPIPE that followed as
        # "failed to load mpg (exit -13)" blames the interpreter for something
        # this process did.
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {shown}, which wrote more than {PROBE_OUTPUT_LIMIT} bytes"
            " without printing mpg's version",
            "Re-run `mpg setup --with-hook` from the environment mpg is installed in",
        )
    if proc.returncode == 0:
        # It ran and succeeded without being mpg. The shape checks cannot see
        # this, and neither can an exit-status probe.
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {shown}, which exits successfully without printing mpg's"
            " version — it is not an interpreter with mpg installed",
            "Re-run `mpg setup --with-hook` from the environment mpg is installed in",
        )
    return ChannelReport(
        CHANNEL_HOOK,
        DEGRADED,
        f"the hook runs {shown}, which failed to load mpg (exit {proc.returncode})",
        "Install mpg into that interpreter, or re-run `mpg setup --with-hook` from one with it",
    )


def _probe_start_failure(command: str, exc: OSError) -> ChannelReport:
    """Classify a failure to start the child.

    Not everything here is "could not be measured". `FileNotFoundError`,
    `PermissionError`, and `ENOEXEC` mean the thing cannot be executed at all —
    Claude Code spawning the same hook meets the same wall, so that is a
    measured failure and belongs in `degraded`. Anything else is this process
    hitting a limit of its own (out of file descriptors, out of memory), which
    says nothing about the registration.
    """
    if isinstance(exc, FileNotFoundError | PermissionError) or exc.errno == errno.ENOEXEC:
        return ChannelReport(
            CHANNEL_HOOK,
            DEGRADED,
            f"the hook runs {command}, which cannot be executed ({exc.strerror or exc})",
            "Run `mpg setup --with-hook` to re-point it",
        )
    return ChannelReport(
        CHANNEL_HOOK,
        UNKNOWN,
        f"could not start {command} ({exc.strerror or exc}), so whether it can load mpg"
        " was not established",
    )


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    """SIGKILL the child's whole process group, tolerating a race with its exit."""
    with contextlib.suppress(OSError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def _probe_reports(
    found: list[tuple[dict, dict]], shape_reports: list[ChannelReport], path: Path
) -> list[ChannelReport]:
    """Probe the interpreters of entries whose shape already checks out.

    Only those: an entry already reported `degraded` for pointing at something
    that is not a file has nothing to gain from being executed, and executing it
    is the expensive, dangerous half of this command.

    Commands are made absolute before running, against the same cwd the shape
    checks used. A relative `command` would otherwise be checked here and
    executed in the sandbox directory — two different files, with the verdict
    from one attached to the other.

    `abspath`, not `resolve`: following symlinks is wrong here. `mpg setup`
    registers `sys.executable`, which in a virtualenv is a link into the base
    installation — and the base installation is exactly where mpg is not
    installed. Resolving it reports every venv-registered hook as broken, which
    this found by failing on the healthy control.
    """
    seen: set[str] = set()
    reports: list[ChannelReport] = []
    for (_, entry), shape in zip(found, shape_reports, strict=True):
        if shape.state != PRESENT:
            continue
        command = entry.get("command", "")
        if not isinstance(command, str) or not command:
            continue
        # `absolute`, not `resolve`: see this function's docstring. It leaves
        # `..` in place, so two spellings of one path are probed twice — a
        # de-duplication miss bounded by PROBE_LIMIT, not a correctness one.
        resolved = str(Path(command).absolute())
        if resolved in seen:
            continue
        if len(seen) >= PROBE_LIMIT:
            reports.append(
                ChannelReport(
                    CHANNEL_HOOK,
                    UNKNOWN,
                    f"{path} names more than {PROBE_LIMIT} distinct interpreters;"
                    " the rest were not run",
                )
            )
            break
        seen.add(resolved)
        # A relative command is executed as an absolute path, and this line is
        # the only record of what ran — the one place in `doctor` that executes
        # anything. Naming both keeps the report readable without leaving the
        # audit trail pointing at a path that depends on where the reader stood.
        shown = command if resolved == command else f"{command} ({resolved})"
        reports.append(_probe_interpreter(resolved, shown=shown))
    return reports


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


def diagnose_all(
    project_dir: Path | None = None, *, run_interpreter: bool = False
) -> list[ChannelReport]:
    """One report per entry in `CHANNELS`, in that order.

    The hook channel is called by name rather than through the table because it
    is the only one the flag means anything to. Widening the table's signature
    would put `run_interpreter` on three diagnosers that ignore it, which reads
    as though they might not — and the whole point of this flag is that a reader
    can tell exactly what executes.
    """
    return [
        diagnose_hook(project_dir, run_interpreter=run_interpreter)
        if name == CHANNEL_HOOK
        else _DIAGNOSERS[name](project_dir)
        for name in CHANNELS
    ]


def summarize(reports: list[ChannelReport]) -> int:
    """The exit status for a set of reports.

    Empty input is 2, not 0. A run that evaluated nothing has not established
    that anything is healthy, and returning 0 for it would make "everything is
    fine" indistinguishable from "nothing was measured" — the failure this
    command exists to catch, committed by the command itself.
    """
    if not reports:
        return 2
    return max(_SEVERITY[report.state] for report in reports)
