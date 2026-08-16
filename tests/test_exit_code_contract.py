"""The exit-code table in design.md, checked against what the commands do.

VERSIONING freezes the rows of that table, not "exit-code semantics". The
distinction is the point of this file. Comparing the table against a set of
scenarios proves that the document and the tests agree; it does not prove that
the implementation has no other exits. A new `sys.exit(3)` added to a command
and mentioned in neither place passes everything here.

Reading the exits out of the source instead would not close that gap either:
`setup` and `uninstall` exit with a variable (`sys.exit(code)`), argparse
produces its own exits, and a signal bypasses the interpreter altogether — a
scan would miss those and could not say that it had. So the freeze covers the
enumerated rows, the exclusions are written down beside the table, and the one
thing checked here is that every row is measured and that what it says is true.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from functools import cache
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import design_md_section

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN = [sys.executable, "-m", "modern_python_guidance"]


def _env() -> dict[str, str]:
    """The child's environment, with this checkout's `src/` importable."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(*args: str) -> int:
    return subprocess.run(
        [*BIN, *args],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=30,
        input="",
    ).returncode


_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|$")


@cache
def documented_exit_codes() -> dict[tuple[str, str], int]:
    """The table rows as ``(command, condition) -> code``.

    Cached because the parametrize decorator reads it once per collection and
    every parametrized case reads it again; the file does not change during a
    run. Callers treat the result as read-only.
    """
    rows: dict[tuple[str, str], int] = {}
    for line in design_md_section("### Exit codes").splitlines():
        m = _ROW.match(line.strip())
        if m:
            rows[(m.group(1), m.group(2))] = int(m.group(3))
    assert rows, "docs/design.md: the Exit codes table parsed to nothing"
    return rows


def _outdated_file(tmp_path: Path) -> str:
    p = tmp_path / "outdated.py"
    p.write_text("import pickle\n")
    return str(p)


def _clean_file(tmp_path: Path) -> str:
    p = tmp_path / "clean.py"
    p.write_text("x: list[str] = []\n")
    return str(p)


SETUP_STEPS = ("setup_mcp", "setup_skills", "setup_rules", "setup_hook")
UNINSTALL_STEPS = ("uninstall_mcp", "uninstall_skills", "uninstall_rules", "uninstall_hook")


def _flattened_rule_project(tmp_path: Path) -> str:
    """A project whose rule symlink has been replaced by a real file.

    One degraded channel is enough for the row, and this is the shape that
    actually happened: a symlink flattened by tooling, its content frozen while
    the packaged rule moved on. The other three read `absent` — nothing else is
    set up here, and `_doctor_status` puts `claude` out of reach so the MCP
    channel cannot vary with the machine — and `absent` does not change what
    "any channel is degraded" produces.
    """
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "modern-python.md").write_text("flattened into a real file\n")
    return str(tmp_path)


def _doctor_status(argv: list[str], extra: tuple[str, dict] | None = None) -> int:
    """`doctor`'s exit status, in-process and with `claude` off the PATH.

    In-process, unlike most rows here, for two reasons.

    The MCP channel asks `claude mcp get`, which reads a *user-scoped*
    registration belonging to whoever runs the tests. Through `_run` these rows
    would pass or fail by the state of a developer's machine — and the exact
    breakage this command was written to find, a registration pinned to a
    replaced interpreter, is what would turn the exit-0 row red. Forcing
    `shutil.which` to None puts every machine in the state CI is already in:
    no `claude`, so the MCP channel reads `absent`. The row then measures
    "present or absent" with absent alone, which satisfies it; a healthy tree
    with all four channels `present` is measured in `test_doctor.py` instead.

    And `unknown` cannot be produced from outside at all without breaking the
    installation the tests run from. That patch names `doctor`'s own binding:
    it imports `_find_skills_dir` at module load, so patching `setup_cmd`'s
    copy would leave the function `doctor` actually calls untouched and the row
    would silently measure the healthy path.
    """
    from modern_python_guidance import cli

    with ExitStack() as stack:
        stack.enter_context(_preserved_sigpipe())
        stack.enter_context(patch("shutil.which", return_value=None))
        if extra is not None:
            target, kwargs = extra
            stack.enter_context(patch(target, **kwargs))
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
    return 0 if exit_info.value.code is None else int(exit_info.value.code)


@contextmanager
def _preserved_sigpipe() -> Iterator[None]:
    """Put the SIGPIPE disposition back after calling `main()` in-process.

    `main()` sets it to `SIG_DFL` and does not restore it, which is correct for
    a process that is about to exit and wrong to leave behind in the pytest
    process: the disposition is global, so it would outlive this test and turn
    a later write to a closed pipe into the death of the runner rather than a
    `BrokenPipeError`. Restored here rather than in `main()` — the command is
    right to want it for its own process.
    """
    try:
        previous = signal.getsignal(signal.SIGPIPE)
    except (AttributeError, ValueError):  # no SIGPIPE on this platform
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGPIPE, previous)


def _exit_status(
    module: str, steps: tuple[str, ...], argv: list[str], failing: str | None = None
) -> int:
    """The status `main()` exits with, every step of the command stubbed.

    Not the value `run_setup` returns. The table promises the status the
    *process* exits with, and `cli._cmd_setup` is the line that turns one into
    the other (`sys.exit(run_setup(...))`) — reading the return value directly
    would keep passing if that line became `sys.exit(0)` or dropped the result.

    Stubbed rather than run because the steps write to the filesystem and
    register MCP configuration outside the repo, which is why `test_setup.py`
    stubs them too. What is left unstubbed is the wiring under test.
    """
    from modern_python_guidance import cli

    with ExitStack() as stack:
        stack.enter_context(_preserved_sigpipe())
        for step in steps:
            stack.enter_context(
                patch(f"modern_python_guidance.{module}.{step}", return_value=step != failing)
            )
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
    return 0 if exit_info.value.code is None else int(exit_info.value.code)


def _every_single_step_failure(module: str, steps: tuple[str, ...], argv: list[str]) -> int:
    """One run per step, each with that step alone failing.

    "any step fails" is a single row, so failing all four at once would satisfy
    it without establishing that one is enough. Disagreement among the four is
    reported here rather than collapsed into whichever value came last.
    """
    codes = {step: _exit_status(module, steps, argv, failing=step) for step in steps}
    distinct = set(codes.values())
    assert len(distinct) == 1, f"single-step failures disagree: {codes}"
    return distinct.pop()


# One entry per table row. Inputs lean on the catalog as little as they can: a
# category no guide declares empties the result whatever the catalog holds,
# while a nonsense query does not — `search` falls back to fuzzy matching and
# returns a hit. "No guide declares it" is a chosen name, not a guarantee;
# `category` is free-form, so a guide adopting `no-such-category` would make
# these rows non-empty. The rows that need a hit — the two `check` matches, and
# the success rows naming a guide id — depend on the catalog outright. Both
# kinds of dependency are noted under the table in design.md.
SCENARIOS: dict[tuple[str, str], object] = {
    ("mpg", "invoked with no command"): lambda tmp: _run(),
    ("search", "at least one guide matches"): lambda tmp: _run(
        "search", "typing", "--format", "json"
    ),
    ("search", "no guide matches the filters"): lambda tmp: _run(
        "search", "typing", "--category", "no-such-category", "--format", "json"
    ),
    ("retrieve", "every requested id resolves"): lambda tmp: _run(
        "retrieve", "use-builtin-generics", "--format", "json"
    ),
    ("retrieve", "the id list is empty"): lambda tmp: _run("retrieve", ",", "--format", "json"),
    ("retrieve", "any requested id is unknown"): lambda tmp: _run(
        "retrieve", "no-such-guide", "--format", "json"
    ),
    ("list", "at least one guide remains after filters"): lambda tmp: _run(
        "list", "--format", "json"
    ),
    ("list", "no guide remains after filters"): lambda tmp: _run(
        "list", "--category", "no-such-category", "--format", "json"
    ),
    ("check", "no outdated pattern found"): lambda tmp: _run(
        "check", _clean_file(tmp), "--format", "json"
    ),
    ("check", "at least one outdated pattern found"): lambda tmp: _run(
        "check", _outdated_file(tmp), "--format", "json"
    ),
    ("check", "patterns found and `--exit-zero` given"): lambda tmp: _run(
        "check", _outdated_file(tmp), "--exit-zero", "--format", "json"
    ),
    ("check", "the file cannot be read"): lambda tmp: _run(
        "check", str(tmp / "absent.py"), "--format", "json"
    ),
    ("detect-version", "a version resolves"): lambda tmp: _run(
        "detect-version", "--project-dir", str(tmp)
    ),
    ("mcp", "stdin reaches end of file"): lambda tmp: _run("mcp"),
    ("setup", "every step succeeds"): lambda tmp: _exit_status(
        "setup_cmd", SETUP_STEPS, ["setup", "--project-dir", str(tmp)]
    ),
    ("setup", "any step fails"): lambda tmp: _every_single_step_failure(
        "setup_cmd", SETUP_STEPS, ["setup", "--project-dir", str(tmp)]
    ),
    ("setup", "mutually exclusive options combined"): lambda tmp: _run(
        "setup", "--mcp-only", "--skills-only"
    ),
    ("uninstall", "every step succeeds"): lambda tmp: _exit_status(
        "uninstall_cmd", UNINSTALL_STEPS, ["uninstall", "--project-dir", str(tmp)]
    ),
    ("uninstall", "any step fails"): lambda tmp: _every_single_step_failure(
        "uninstall_cmd", UNINSTALL_STEPS, ["uninstall", "--project-dir", str(tmp)]
    ),
    ("uninstall", "mutually exclusive options combined"): lambda tmp: _run(
        "uninstall", "--mcp-only", "--skills-only"
    ),
    ("doctor", "every channel is present or absent"): lambda tmp: _doctor_status(
        ["doctor", "--project-dir", str(tmp)]
    ),
    ("doctor", "any channel is degraded"): lambda tmp: _doctor_status(
        ["doctor", "--project-dir", _flattened_rule_project(tmp)]
    ),
    ("doctor", "any channel cannot be determined"): lambda tmp: _doctor_status(
        ["doctor", "--project-dir", str(tmp)],
        (
            "modern_python_guidance.doctor._find_skills_dir",
            {"side_effect": FileNotFoundError("cannot locate the bundled skills")},
        ),
    ),
    (
        "doctor",
        "`--project-dir` names something that is not a directory",
    ): lambda tmp: _run("doctor", "--project-dir", str(tmp / "no-such-directory")),
}


def test_every_documented_row_is_measured() -> None:
    """The table and the scenarios name the same rows.

    Without this, a row can be added to design.md and never exercised — the
    per-row assertions below only visit rows that appear in both. A frozen
    surface with a row nobody measures is the state VERSIONING exists to
    prevent, one table cell at a time.
    """
    documented = set(documented_exit_codes())
    measured = set(SCENARIOS)
    assert documented == measured, (
        f"documented but not measured: {sorted(documented - measured)}; "
        f"measured but not documented: {sorted(measured - documented)}"
    )


@pytest.mark.parametrize("row", sorted(documented_exit_codes()))
def test_documented_exit_code_is_the_observed_one(row: tuple[str, str], tmp_path: Path) -> None:
    expected = documented_exit_codes()[row]
    observed = SCENARIOS[row](tmp_path)  # type: ignore[operator]
    command, condition = row
    assert observed == expected, (
        f"design.md says `{command}` exits {expected} when {condition}, observed {observed}"
    )


def test_calling_main_in_process_leaves_no_signal_disposition_behind(tmp_path: Path) -> None:
    """The restoration above, held rather than trusted.

    Several rows call `main()` in this process, and `main()` sets SIGPIPE to
    `SIG_DFL` without putting it back. Left in place, the change outlives the
    test and belongs to the runner: a later write to a closed pipe would kill
    pytest instead of raising `BrokenPipeError`. That failure would surface far
    from here, in whatever test happened to run next, so the invariant is
    checked where it is created.

    The disposition is set here rather than read: reading it first makes this
    test pass whenever an earlier row has already left `SIG_DFL` behind, since
    `main()` then "changes" it to the value it already had. Measured — with the
    restoration disabled the whole file still passed, and only this test run
    alone failed. Planting a known value makes the check independent of what
    ran before it.
    """
    sentinel = signal.SIG_IGN
    previous = signal.signal(signal.SIGPIPE, sentinel)
    try:
        _exit_status("setup_cmd", SETUP_STEPS, ["setup", "--project-dir", str(tmp_path)])
        assert signal.getsignal(signal.SIGPIPE) is sentinel, (
            "calling main() in-process changed this process's SIGPIPE disposition"
        )
    finally:
        signal.signal(signal.SIGPIPE, previous)


def test_the_table_states_what_it_does_not_cover() -> None:
    """The exclusions are part of the guarantee, not an omission from it.

    A reader who takes the table for "every way mpg can exit" would conclude
    that 2 always means bad usage and that a crash is distinguishable from an
    empty result. Neither holds, so the section says so; this keeps the saying
    from being dropped while the table stays.
    """
    section = design_md_section("### Exit codes")
    for topic in ("argparse", "signal", "Uncaught exceptions", "`hook`"):
        assert topic in section, f"the Exit codes section no longer excludes {topic}"


def test_signal_termination_is_outside_the_table() -> None:
    """The premise of one exclusion, measured rather than asserted.

    `main()` restores the default SIGPIPE disposition, so a closed pipe kills
    the process instead of raising BrokenPipeError. If that ever changed, the
    exclusion would still be written down while describing nothing — and a
    caller reading the table would keep being told to expect 141.
    """
    producer = subprocess.Popen(
        [*BIN, "list", "--with-content", "--format", "json"],
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert producer.stdout is not None
    producer.stdout.close()  # the reader goes away before the writer finishes
    status = producer.wait(timeout=30)
    # Death by signal, specifically. "Non-zero" would also accept the 1 an
    # ordinary traceback produces, which is the outcome design.md says does
    # *not* happen here. Python reports a signal as its negation; the 141 the
    # document quotes is the same event as a shell renders it (128 + 13).
    assert status == -signal.SIGPIPE, (
        f"a closed pipe produced status {status}, not termination by SIGPIPE;"
        " design.md's exclusion now describes a path that does not exist"
    )
    assert 128 + signal.SIGPIPE == 141, "the shell-visible number quoted in design.md"


def test_json_output_survives_the_documented_success_rows() -> None:
    """Exit 0 with unparseable output would satisfy the table and help nobody.

    The status is what the table freezes, but a status is only worth freezing
    if it accompanies the output the caller came for.
    """
    result = subprocess.run(
        [*BIN, "list", "--format", "json"],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert isinstance(json.loads(result.stdout), list)
