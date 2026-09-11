"""`mpg doctor` against a project that is trying to take its report away.

The promise, from README "Check the install": apart from `--run-interpreter`
and whatever `claude mcp get` starts, nothing a project holds can take the
report away from `doctor` — it finishes, printing one line per channel (and its
fix) that it wrote itself, and exits by the table in `docs/design.md`.

Every project built here broke that promise before this change: it hung
(#242, a fifo), ended in a traceback (#246, an unreadable directory, content
Python cannot finish parsing), answered "healthy" for a directory it never
looked into (3.14), or wrote a line of the report itself (#245). The tests that
could hang run in a child process with a timeout, so a regression fails instead
of stalling the suite.
"""

from __future__ import annotations

import errno
import itertools
import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pytest

from modern_python_guidance import cli, doctor, hook_config, setup_cmd
from modern_python_guidance.doctor import (
    ABSENT,
    CHANNEL_HOOK,
    CHANNEL_MCP,
    CHANNEL_SKILLS,
    CHANNELS,
    DEGRADED,
    UNKNOWN,
    diagnose_all,
    diagnose_hook,
    diagnose_rules,
    diagnose_skills,
    summarize,
)

CANONICAL_ARGS = ["-m", "modern_python_guidance", "hook", "claude-post-tool-use"]

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file types and modes")
needs_permissions = pytest.mark.skipif(
    IS_ROOT or sys.platform == "win32", reason="root reads through directory permissions"
)

# What `_printable` renders visibly. Counted with the running interpreter's own
# `unicodedata`, never a hard-coded list: the Unicode version differs across
# the interpreters CI runs (seven characters are Cn on 3.11 and Cf on 3.14).
ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})


def _write_settings(
    project: Path, *, command: str = "/usr/bin/env", matcher: str = "Edit|Write"
) -> Path:
    """A settings file with one mpg entry, written as real JSON.

    `json.dumps` escapes what a hand-built string could not carry: a newline,
    a NUL, and a lone surrogate all arrive in the file as `\\n`, `\\u0000`,
    `\\ud800` and come back out of `json.loads` as the characters themselves.
    """
    path = project / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"type": "command", "command": command, "args": CANONICAL_ARGS}
    path.write_text(
        json.dumps({"hooks": {"PostToolUse": [{"matcher": matcher, "hooks": [entry]}]}})
    )
    return path


def _write_raw_settings(project: Path, raw: bytes) -> Path:
    path = project / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".claude").mkdir(parents=True)
    (root / ".git").mkdir()
    return root


@pytest.fixture
def locked(tmp_path: Path):
    """A directory nobody but root can look into, holding one subdirectory.

    A link to `locked/inner` is the shape a cloned repository can deliver:
    git carries symlinks, and the target need not be anywhere the user can read.
    """
    directory = tmp_path / "locked"
    (directory / "inner").mkdir(parents=True)
    directory.chmod(0)
    yield directory
    directory.chmod(0o700)


def _replace_claude_with_link(project: Path, target: str | Path) -> None:
    (project / ".claude").rmdir()
    (project / ".claude").symlink_to(target)


# --- #242: a matcher is answered, and answered in time proportional to its length ---

ALPHABET = "tEWex.^$*|\n"
"""Letters from both tool names and from neither, every metacharacter the
portable subset admits, and the newline it also admits."""

TOOLS = ("Edit", "Write")


def _compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _patterns_up_to(length: int):
    for size in range(length + 1):
        for combo in itertools.product(ALPHABET, repeat=size):
            yield "".join(combo)


class TestTheSubsetIsEvaluatedWithoutRe:
    """`re` is kept out of the matcher path entirely — the compiler as well as
    the matcher. Backtracking made `".*" * 200 + "Z"` run past twenty seconds;
    `re.compile` alone is quadratic in two branches sharing a prefix, thirty
    to sixty-eight seconds at a million characters. Both were measured.

    What replaces them is only safe because it gives the same answers, so the
    first two tests compare it with `re` on every pattern up to length four.
    That is where equivalence with JavaScript was measured (#237), and the
    claim here is the other half of the chain: this evaluator agrees with the
    Python engine that was measured to agree with node.
    """

    def test_the_syntax_rule_is_the_one_re_compile_applies(self) -> None:
        disagree = [
            p for p in _patterns_up_to(4) if hook_config._subset_syntax_ok(p) != _compiles(p)
        ]
        assert disagree == []

    def test_the_evaluator_answers_what_re_search_answers(self) -> None:
        checked = 0
        disagree = []
        for pattern in _patterns_up_to(4):
            if not _compiles(pattern):
                continue
            for tool in TOOLS:
                checked += 1
                if hook_config._subset_search(pattern, tool) != (
                    re.search(pattern, tool) is not None
                ):
                    disagree.append((pattern, tool))
        assert disagree == []
        # Not vacuous: an alphabet that stopped compiling would agree trivially.
        assert checked > 20_000

    def test_longer_patterns_agree_as_well(self) -> None:
        rng = random.Random(242)
        checked = 0
        while checked < 4_000:
            pattern = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(6, 30)))
            # Bounded so `re` itself terminates — it is the reference here.
            if pattern.count("*") > 12 or not _compiles(pattern):
                continue
            for tool in TOOLS:
                checked += 1
                assert hook_config._subset_search(pattern, tool) == (
                    re.search(pattern, tool) is not None
                ), (pattern, tool)

    # (matcher, what it answers for "Write"). Each one broke `re` measurably.
    PATHOLOGICAL = (
        (".*" * 200 + "Z", False),  # catastrophic backtracking: > 20 s
        (".*" * 200 + "t", True),
        ("^" + "a" * 499_999 + "|^" + "a" * 499_999, False),  # quadratic compile: > 30 s
        ("t*" * 50_000, True),
        ("x." * 150_000 + "|" + "x." * 150_000, False),
        ("x.|" * 300_000 + "x.", False),  # many branches
    )

    CHILD = (
        "import json, sys, time\n"
        "from modern_python_guidance.hook_config import matcher_fires_on\n"
        "out = []\n"
        "for matcher in json.loads(sys.stdin.read()):\n"
        "    started = time.monotonic()\n"
        "    answer = matcher_fires_on(matcher, 'Write')\n"
        "    out.append([answer, time.monotonic() - started])\n"
        "print(json.dumps(out))\n"
    )

    def test_a_pathological_matcher_is_answered_within_a_second(self) -> None:
        """In a child, so a regression is a failed test rather than a hung suite."""
        payload = json.dumps([matcher for matcher, _ in self.PATHOLOGICAL])
        proc = subprocess.run(
            [sys.executable, "-c", self.CHILD],
            input=payload,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        results = json.loads(proc.stdout)
        for (matcher, expected), (answer, seconds) in zip(self.PATHOLOGICAL, results, strict=True):
            label = f"{matcher[:12]!r}… ({len(matcher)} chars)"
            assert answer is expected, label
            assert seconds < 1.0, f"{label} took {seconds:.2f}s"


# --- settings files this process cannot finish reading ---

LIMIT = 1 << 20

UNPARSABLE = (
    pytest.param(b'{"x": "\xff"}', id="bytes that are not UTF-8"),
    pytest.param(b'{"x": ' + b"1" * 5000 + b"}", id="an integer too long to convert"),
    pytest.param(b"[" * 200_000 + b"]" * 200_000, id="nesting too deep"),
    pytest.param(b'{"x": NaN}', id="NaN"),
    pytest.param(b'{"x": -Infinity}', id="Infinity"),
    pytest.param(b'{"x": "' + b"a" * LIMIT + b'"}', id="more than 1 MiB"),
)


class TestReadSettings:
    @pytest.mark.parametrize("raw", UNPARSABLE)
    def test_content_it_cannot_finish_parsing_is_unparsable(
        self, tmp_path: Path, raw: bytes
    ) -> None:
        path = tmp_path / "settings.local.json"
        path.write_bytes(raw)
        with pytest.raises(hook_config.HookConfigUnparsable):
            hook_config.read_settings(path)

    def test_invalid_json_stays_a_plain_config_error(self, tmp_path: Path) -> None:
        """The control: a syntax error is one both engines refuse, so it is
        still `HookConfigError` — and still `degraded` in doctor."""
        path = tmp_path / "settings.local.json"
        path.write_text("{ not json")
        with pytest.raises(hook_config.HookConfigError) as caught:
            hook_config.read_settings(path)
        assert not isinstance(caught.value, hook_config.HookConfigUnparsable)

    def test_a_file_of_exactly_the_limit_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.local.json"
        path.write_bytes(b"{}" + b" " * (LIMIT - 2))
        assert hook_config.read_settings(path) == {}

    @posix_only
    def test_a_fifo_is_refused_rather_than_waited_on(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.local.json"
        os.mkfifo(path)
        code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from modern_python_guidance import hook_config as h\n"
            "try:\n"
            "    h.read_settings(Path(sys.argv[1]))\n"
            "except h.HookConfigError as e:\n"
            "    print(type(e).__name__, e)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=10
        )
        assert proc.stdout.startswith("HookConfigError "), proc.stdout + proc.stderr
        assert "not a regular file" in proc.stdout


# --- the channels themselves ---


class TestPathsTheOsWillNotLookUp:
    """#246. A registered path the OS refuses is `degraded`: Claude Code meets
    the same wall spawning it. `Path.exists()` raised here on 3.11-3.13."""

    @pytest.mark.parametrize("command", ["x" * 100_001, "/usr/bin/\x00env", "/usr/bin/\ud800env"])
    def test_a_command_the_os_cannot_look_up_is_degraded(
        self, project: Path, command: str
    ) -> None:
        _write_settings(project, command=command)
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "cannot be reached" in report.detail

    @pytest.mark.parametrize(
        ("diagnose", "link"),
        [
            (diagnose_skills, Path(".claude/skills/modern-python-guidance")),
            (diagnose_rules, Path(".claude/rules/modern-python.md")),
        ],
    )
    def test_a_link_whose_destination_the_os_cannot_look_up_is_degraded(
        self, project: Path, diagnose: Callable, link: Path
    ) -> None:
        path = project / link
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to("/" + "y" * 300 + "/" + link.name)
        report = diagnose(project)
        assert report.state == DEGRADED
        assert "cannot be reached" in report.detail


ALL_PROJECT_CHANNELS = [diagnose_skills, diagnose_rules, diagnose_hook]


class TestPathsDoctorCannotLookUp:
    """Principle: only an OS answer of "nothing there" may read as `absent`.

    `absent` exits 0, so a directory `doctor` never looked into must not reach
    it. 3.14's pathlib turns EACCES into False, which made an unreadable
    `.claude` read as a healthy, uninstalled project; 3.11-3.13 raised instead.
    """

    @needs_permissions
    @pytest.mark.parametrize("diagnose", ALL_PROJECT_CHANNELS)
    def test_an_unreadable_claude_directory_is_unknown(
        self, project: Path, locked: Path, diagnose: Callable
    ) -> None:
        _replace_claude_with_link(project, locked / "inner")
        report = diagnose(project)
        assert report.state == UNKNOWN
        assert "cannot look up" in report.detail

    @pytest.mark.parametrize("diagnose", ALL_PROJECT_CHANNELS)
    def test_a_claude_directory_that_points_at_itself_is_unknown(
        self, project: Path, diagnose: Callable
    ) -> None:
        """ELOOP is not "nothing there": Claude Code cannot read through it and
        `setup` cannot repair it (its `mkdir` meets the link)."""
        _replace_claude_with_link(project, ".claude")
        report = diagnose(project)
        assert report.state == UNKNOWN

    @pytest.mark.parametrize("diagnose", ALL_PROJECT_CHANNELS)
    def test_the_look_up_does_not_depend_on_which_interpreter_runs(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, diagnose: Callable
    ) -> None:
        """The same refusal on every interpreter, without relying on chmod.

        With the check removed, 3.11-3.13 raise out of `link_state` or
        `read_settings`, and 3.14 answers `absent` — each fails here.
        """
        real_lstat = os.lstat

        def refuse(path, *args, **kwargs):
            if ".claude" in os.fspath(path):
                raise PermissionError(errno.EACCES, "Permission denied", os.fspath(path))
            return real_lstat(path, *args, **kwargs)

        monkeypatch.setattr(os, "lstat", refuse)
        report = diagnose(project)
        assert report.state == UNKNOWN
        assert "Permission denied" in report.detail

    def test_an_empty_claude_directory_is_still_absent(self, project: Path) -> None:
        """The control: nothing there, measured, is `absent` — the check did
        not turn every lookup into `unknown`."""
        for diagnose in ALL_PROJECT_CHANNELS:
            assert diagnose(project).state == ABSENT


class TestSettingsDoctorCannotFinishParsing:
    """Python refusing a file does not mean Claude Code refuses it — Node
    reads invalid UTF-8 inside a string, and huge integers — so these are
    `unknown`, never `degraded`. They used to end `doctor` in a traceback, and
    `NaN` used to be read the Python way and judged."""

    @pytest.mark.parametrize("raw", UNPARSABLE)
    def test_content_it_cannot_finish_parsing_is_unknown(self, project: Path, raw: bytes) -> None:
        _write_raw_settings(project, raw)
        report = diagnose_hook(project)
        assert report.state == UNKNOWN
        assert "settings.local.json" in report.detail

    def test_invalid_json_is_still_degraded(self, project: Path) -> None:
        _write_raw_settings(project, b"{ not json")
        assert diagnose_hook(project).state == DEGRADED


class TestOneChannelFailingDoesNotTakeTheOthers:
    """The backstop is for a shape nobody has found yet, so it is tested with
    a failure invented for the purpose. Nothing above relies on it: each hole
    found so far is closed with its own verdict."""

    def test_an_unexpected_exception_is_unknown_for_that_channel_only(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_project_dir=None):
            raise RuntimeError("a failure nobody has found yet")

        monkeypatch.setitem(doctor._DIAGNOSERS, CHANNEL_SKILLS, boom)
        monkeypatch.setattr(doctor.shutil, "which", lambda *_, **__: None)
        reports = diagnose_all(project)
        assert [report.channel for report in reports] == list(CHANNELS)
        by_channel = {report.channel: report for report in reports}
        assert by_channel[CHANNEL_SKILLS].state == UNKNOWN
        assert "RuntimeError" in by_channel[CHANNEL_SKILLS].detail
        assert "a failure nobody has found yet" in by_channel[CHANNEL_SKILLS].detail
        assert all(r.state != UNKNOWN for c, r in by_channel.items() if c != CHANNEL_SKILLS)
        assert summarize(reports) == 2

    def test_the_hook_channel_is_guarded_as_well(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("hook diagnosis failed")

        monkeypatch.setattr(doctor, "diagnose_hook", boom)
        monkeypatch.setattr(doctor.shutil, "which", lambda *_, **__: None)
        by_channel = {report.channel: report for report in diagnose_all(project)}
        assert by_channel[CHANNEL_HOOK].state == UNKNOWN
        assert by_channel[CHANNEL_MCP].state == ABSENT


class TestProjectRoot:
    def test_a_root_that_cannot_be_determined_keeps_the_mcp_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*_args, **_kwargs):
            raise PermissionError(errno.EACCES, "Permission denied", "somewhere")

        monkeypatch.setattr(doctor, "_find_project_root", refuse)
        monkeypatch.setattr(doctor.shutil, "which", lambda *_, **__: None)
        by_channel = {report.channel: report for report in diagnose_all()}
        assert list(by_channel) == list(CHANNELS)
        assert by_channel[CHANNEL_MCP].state == ABSENT
        for channel in CHANNELS:
            if channel != CHANNEL_MCP:
                assert by_channel[channel].state == UNKNOWN
                assert "project root" in by_channel[channel].detail

    @needs_permissions
    def test_an_unreadable_marker_below_the_root_is_unknown_not_skipped(
        self, tmp_path: Path, locked: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """3.14 skipped the marker and diagnosed a directory further up —
        `$HOME`, when this was measured."""
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        sub = root / "sub"
        sub.mkdir()
        (sub / ".claude").symlink_to(locked / "inner")
        monkeypatch.chdir(sub)
        monkeypatch.setattr(doctor.shutil, "which", lambda *_, **__: None)
        by_channel = {report.channel: report for report in diagnose_all()}
        for channel in CHANNELS:
            if channel != CHANNEL_MCP:
                assert by_channel[channel].state == UNKNOWN, channel

    def test_strict_agrees_with_the_default_on_dangling_and_looped_markers(
        self, tmp_path: Path
    ) -> None:
        """Strict differs from setup's default only in raising — a dangling or
        looped marker is "no marker" to both, so they choose the same root."""
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        dangling = root / "dangling"
        dangling.mkdir()
        (dangling / ".claude").symlink_to(tmp_path / "nowhere")
        looped = root / "looped"
        looped.mkdir()
        (looped / ".claude").symlink_to(".claude")
        for start in (dangling, looped):
            assert setup_cmd._find_project_root(start, strict=True) == root
            assert setup_cmd._find_project_root(start) == root

    @needs_permissions
    def test_strict_raises_where_a_marker_cannot_be_looked_up(
        self, tmp_path: Path, locked: Path
    ) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / ".claude").symlink_to(locked / "inner")
        with pytest.raises(PermissionError):
            setup_cmd._find_project_root(sub, strict=True)


# --- the real command, in a child process ---


def _run_doctor(
    tmp_path: Path,
    *args: str,
    cwd: Path | None = None,
    encoding: str = "utf-8",
    path: str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """`mpg doctor` as a user runs it, with no `claude` on PATH.

    The MCP channel reads `absent` without `claude`, which pins it: what is
    under test is the three channels a project controls. `PYTHONIOENCODING`
    is strict UTF-8 by default, so a lone surrogate reaching `print` is a
    traceback here rather than something a lenient stream quietly absorbs.
    """
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir(exist_ok=True)
    env = {"PATH": path or str(empty_bin), "HOME": str(tmp_path), "PYTHONIOENCODING": encoding}
    return subprocess.run(
        [sys.executable, "-m", "modern_python_guidance", "doctor", *args],
        capture_output=True,
        cwd=cwd or tmp_path,
        env=env,
        timeout=10,
        check=False,
    )


NOTE_PREFIX = "Note: --project-dir"


def _doctor_wrote_every_line(stdout: str, *, with_note: bool) -> list[str]:
    """Assert stdout is exactly doctor's own shape; return the channel lines.

    One line per channel in `CHANNELS` order, each optionally followed by one
    `->` fix line, then — with `--project-dir` — a blank line and the note.
    Anything else is a line doctor did not write.
    """
    lines = stdout.split("\n")
    assert lines[-1] == "", "output does not end in a newline"
    lines.pop()
    if with_note:
        assert lines[-2:-1] == [""] and lines[-1].startswith(NOTE_PREFIX), lines[-2:]
        lines = lines[:-2]
    channel_lines = [line for line in lines if not line.lstrip().startswith("-> ")]
    assert [line.split()[0] for line in channel_lines] == list(CHANNELS), lines
    for line in lines:
        if line in channel_lines:
            assert line.split()[1] in {"present", "degraded", "absent", "unknown"}, line
        else:
            assert line.startswith(" ") and line.lstrip().startswith("-> "), line
    return channel_lines


def _over_long_command(project: Path, _locked: Path | None) -> None:
    _write_settings(project, command="x" * 100_001)


def _nul_in_command(project: Path, _locked: Path | None) -> None:
    _write_settings(project, command="/usr/bin/\x00env")


def _over_long_link_destination(project: Path, _locked: Path | None) -> None:
    link = project / ".claude" / "skills" / "modern-python-guidance"
    link.parent.mkdir(parents=True)
    link.symlink_to("/" + "y" * 300 + "/modern-python-guidance")


def _unreadable_claude(project: Path, locked: Path | None) -> None:
    assert locked is not None
    _replace_claude_with_link(project, locked / "inner")


def _looped_claude(project: Path, _locked: Path | None) -> None:
    _replace_claude_with_link(project, ".claude")


def _fifo_settings(project: Path, _locked: Path | None) -> None:
    os.mkfifo(project / ".claude" / "settings.local.json")


def _linked_but_unreachable(project: Path, _locked: Path | None) -> None:
    """A destination equal to the bundled source as a string, and unreachable."""
    link = project / ".claude" / "skills" / "modern-python-guidance"
    link.parent.mkdir(parents=True)
    link.symlink_to("/" + "y" * 300 + "/.." + str(setup_cmd._find_skills_dir()))


def _raw(raw: bytes) -> Callable[[Path, Path | None], None]:
    def build(project: Path, _locked: Path | None) -> None:
        _write_raw_settings(project, raw)

    return build


# (id, builder, exit status, needs a locked directory)
HOSTILE_PROJECTS = [
    ("an over-long command", _over_long_command, 1, False),
    ("a NUL in command", _nul_in_command, 1, False),
    ("an over-long link destination", _over_long_link_destination, 1, False),
    ("a link that reads as linked and cannot be followed", _linked_but_unreachable, 1, False),
    ("an unreadable .claude", _unreadable_claude, 2, True),
    ("a .claude that points at itself", _looped_claude, 2, False),
    ("a fifo for settings", _fifo_settings, 1, False),
    ("bytes that are not UTF-8", _raw(b'{"x": "\xff"}'), 2, False),
    ("an integer too long to convert", _raw(b'{"x": ' + b"1" * 5000 + b"}"), 2, False),
    ("nesting too deep", _raw(b"[" * 200_000 + b"]" * 200_000), 2, False),
    ("NaN", _raw(b'{"x": NaN}'), 2, False),
    ("more than 1 MiB", _raw(b'{"x": "' + b"a" * LIMIT + b'"}'), 2, False),
]


@posix_only
class TestTheCommandAlwaysFinishes:
    @pytest.mark.parametrize(
        ("build", "status", "wants_locked"),
        [
            pytest.param(build, status, wants, id=name)
            for name, build, status, wants in HOSTILE_PROJECTS
        ],
    )
    def test_a_hostile_project_gets_a_report(
        self, tmp_path: Path, project: Path, build: Callable, status: int, wants_locked: bool
    ) -> None:
        if wants_locked and IS_ROOT:
            pytest.skip("root reads through directory permissions")
        locked = None
        if wants_locked:
            locked = tmp_path / "locked"
            (locked / "inner").mkdir(parents=True)
            locked.chmod(0)
        try:
            build(project, locked)
            proc = _run_doctor(tmp_path, "--project-dir", str(project))
        finally:
            if locked is not None:
                locked.chmod(0o700)
        stderr = proc.stderr.decode(errors="replace")
        assert "Traceback" not in stderr, stderr
        assert proc.returncode == status, proc.stdout.decode(errors="replace") + stderr
        _doctor_wrote_every_line(proc.stdout.decode(), with_note=True)

    @needs_permissions
    def test_run_from_a_subdirectory_with_an_unreadable_marker(
        self, tmp_path: Path, locked: Path
    ) -> None:
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        sub = root / "sub"
        sub.mkdir()
        (sub / ".claude").symlink_to(locked / "inner")
        proc = _run_doctor(tmp_path, cwd=sub)
        stderr = proc.stderr.decode(errors="replace")
        assert "Traceback" not in stderr, stderr
        assert proc.returncode == 2
        _doctor_wrote_every_line(proc.stdout.decode(), with_note=False)


@posix_only
class TestNothingAProjectHoldsCanAddALine:
    """#245. The file wrote `doctor`'s lines: a newline in `command` put a
    fabricated `mcp present` line on screen, with or without a terminal."""

    FORGED = "/nonexistent/py\nmcp        present    registered as modern-python-guidance"

    def test_control_characters_are_shown_not_obeyed(self, tmp_path: Path, project: Path) -> None:
        command = self.FORGED + "\x1b[2K\r\u202e\ud800\n::error::x"
        _write_settings(project, command=command)
        link = project / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        # Raw bytes in a link destination come back from readlink as lone
        # surrogates (surrogateescape) — 0x9B is CSI on an 8-bit terminal.
        os.symlink(b"/nonexistent/\xff\x9b31m", os.fsencode(link))

        proc = _run_doctor(tmp_path, "--project-dir", str(project))
        stderr = proc.stderr.decode(errors="replace")
        assert "Traceback" not in stderr, stderr
        stdout = proc.stdout.decode("utf-8")  # strict: a surrogate would not decode
        channel_lines = _doctor_wrote_every_line(stdout, with_note=True)

        hidden = [
            ch for ch in stdout if ch != "\n" and unicodedata.category(ch) in ESCAPED_CATEGORIES
        ]
        assert hidden == []
        assert not any(line.startswith("::") for line in stdout.split("\n"))
        hook_line = next(line for line in channel_lines if line.startswith("hook"))
        for shown in ("\\x0a", "\\x1b", "\\x0d", "\\u202e", "\\ud800"):
            assert shown in hook_line, shown
        skills_line = next(line for line in channel_lines if line.startswith("skills"))
        assert "\\xff\\x9b31m" in skills_line

    def test_a_terminal_that_is_not_utf8_is_written_ascii(
        self, tmp_path: Path, project: Path
    ) -> None:
        """cp1251 encodes U+2026 as 0x85 (NEL) and U+203A as 0x9B (CSI). Both are
        printable characters, so escaping by category cannot stop them —
        only the encoding can."""
        link = project / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        link.symlink_to("/nonexistent/\u2026\u203a")
        proc = _run_doctor(tmp_path, "--project-dir", str(project), encoding="cp1251")
        assert "Traceback" not in proc.stderr.decode(errors="replace")
        assert all(byte < 0x80 for byte in proc.stdout), proc.stdout
        _doctor_wrote_every_line(proc.stdout.decode("ascii"), with_note=True)
        assert "\\u2026\\u203a" in proc.stdout.decode("ascii")


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("a\nb", "a\\x0ab"),
        ("\x1b[2K", "\\x1b[2K"),
        ("\x85", "\\x85"),
        ("\u2028", "\\u2028"),
        ("\u202e", "\\u202e"),
        ("\U000e0041", "\\U000e0041"),
        ("\udcff", "\\xff"),
        ("\ud800", "\\ud800"),
        ("/プロジェクト — ok", "/プロジェクト — ok"),
        ("", ""),
    ],
)
def test_printable_shows_what_would_have_been_obeyed(raw: str, shown: str) -> None:
    assert cli._printable(raw) == shown


class TestALinkThatReadsAsLinkedButCannotBeFollowed:
    """`link_state` decides "linked" from strings and a non-strict `resolve()`,
    which walks past a component the OS will not look up and lets `..` cancel
    it. Before the fix the branch that followed raised on 3.11-3.13 and, on
    3.14, called the link right and the installation hollow — with a fix of
    reinstalling mpg, for a link that was the problem."""

    @pytest.mark.parametrize("channel", ["skills", "rules"])
    def test_it_is_degraded_as_unreachable(
        self, tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch, channel: str
    ) -> None:
        skills = tmp_path / "installed" / "skills" / "modern-python-guidance"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("---\nname: modern-python-guidance\n---\n")
        rule = tmp_path / "installed" / "rules" / "modern-python.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("---\npaths: []\n---\n")
        monkeypatch.setattr(doctor, "_find_skills_dir", lambda: skills)
        monkeypatch.setattr(doctor, "_find_rule_source", lambda: rule)
        detour = f"{tmp_path}/{'y' * 300}/.."
        if channel == "skills":
            link = project / ".claude" / "skills" / "modern-python-guidance"
            source, diagnose = skills, diagnose_skills
            target = f"{detour}/installed/skills/modern-python-guidance"
        else:
            link = project / ".claude" / "rules" / "modern-python.md"
            source, diagnose = rule, diagnose_rules
            target = f"{detour}/installed/rules/modern-python.md"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        # The branch under test: without this, the case could quietly move to
        # STALE on some interpreter and pass for another reason.
        assert setup_cmd.link_state(link, source) == setup_cmd.LINK_LINKED

        report = diagnose(project)
        assert report.state == DEGRADED
        assert "cannot be reached" in report.detail
        assert "Reinstall" not in report.fix


class TestWhichClaudeRuns:
    """A relative PATH entry resolves against the working directory — usually
    the project — so the `claude` it finds may be one the project ships."""

    def test_a_claude_found_through_a_relative_entry_is_not_run(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def which(_cmd, path=None):
            # Nothing on the absolute entries; one under a relative entry.
            return None if path is not None else "node_modules/.bin/claude"

        monkeypatch.setattr(doctor.shutil, "which", which)

        def must_not_run(*_args, **_kwargs):
            raise AssertionError("ran a claude the project may have supplied")

        monkeypatch.setattr(doctor, "_run_claude_mcp_quiet", must_not_run)
        report = doctor.diagnose_mcp(project)
        assert report.state == UNKNOWN
        assert "relative entry" in report.detail

    def test_an_absolute_claude_is_used_and_runs_without_relative_entries(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative entry ahead of an absolute one no longer decides: the
        absolute `claude` is found, and the `PATH` it runs with has no
        relative entries for its `#!/usr/bin/env node` to find a `node` on."""
        monkeypatch.setenv(
            "PATH", os.pathsep.join(["node_modules/.bin", "", "/opt/cc/bin", "/bin"])
        )
        asked = []

        def which(_cmd, path=None):
            asked.append(path)
            return "/opt/cc/bin/claude" if path is not None else "node_modules/.bin/claude"

        monkeypatch.setattr(doctor.shutil, "which", which)
        ran = []

        def run(cmd, cwd=None, env=None):
            ran.append((cmd, env))

        monkeypatch.setattr(doctor, "_run_claude_mcp_quiet", run)
        doctor.diagnose_mcp(project)
        assert asked == ["/opt/cc/bin" + os.pathsep + "/bin"]
        ((cmd, env),) = ran
        assert cmd[0] == "/opt/cc/bin/claude"
        assert env["PATH"].split(os.pathsep) == ["/opt/cc/bin", "/bin"]

    @posix_only
    def test_the_real_command_does_not_run_it(self, tmp_path: Path, project: Path) -> None:
        marker = tmp_path / "PROJECT-CLAUDE-RAN"
        fake = project / "node_modules" / ".bin" / "claude"
        fake.parent.mkdir(parents=True)
        fake.write_text(f'#!/bin/sh\n: > "{marker}"\n')
        fake.chmod(0o755)
        proc = _run_doctor(tmp_path, cwd=project, path="node_modules/.bin")
        assert "Traceback" not in proc.stderr.decode(errors="replace")
        assert not marker.exists()
        mcp_line = _doctor_wrote_every_line(proc.stdout.decode(), with_note=False)[0]
        assert mcp_line.split()[:2] == ["mcp", "unknown"]
        assert proc.returncode == 2

    @posix_only
    @pytest.mark.parametrize("from_elsewhere", [False, True], ids=["cwd", "project-dir"])
    def test_claudes_interpreter_is_not_taken_from_the_project(
        self, tmp_path: Path, project: Path, from_elsewhere: bool
    ) -> None:
        """An npm `claude` is a `#!/usr/bin/env node` script. On an absolute
        entry it is the user's; the `node` it asks `env` for came from a
        relative entry — the project's `node_modules/.bin` — until `claude`
        ran with those entries dropped. With `--project-dir` the child's cwd is
        the project too, so the relative entry resolved there as well."""
        marker = tmp_path / "PROJECT-INTERPRETER-RAN"
        interpreter = project / "node_modules" / ".bin" / "mpg-fake-node"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text(
            f'#!/bin/sh\n: > "{marker}"\necho "No MCP server named x" >&2\nexit 1\n'
        )
        interpreter.chmod(0o755)
        user_bin = tmp_path / "user-bin"
        user_bin.mkdir()
        claude = user_bin / "claude"
        claude.write_text("#!/usr/bin/env mpg-fake-node\n")
        claude.chmod(0o755)
        path = os.pathsep.join(["node_modules/.bin", str(user_bin), "/usr/bin", "/bin"])
        if from_elsewhere:
            proc = _run_doctor(tmp_path, "--project-dir", str(project), path=path)
        else:
            proc = _run_doctor(tmp_path, cwd=project, path=path)
        assert "Traceback" not in proc.stderr.decode(errors="replace")
        assert not marker.exists()
        mcp_line = _doctor_wrote_every_line(proc.stdout.decode(), with_note=from_elsewhere)[0]
        # The project's `node` answered "absent" and exit 0; with no `node`
        # found, `claude` fails to start and the channel is not established.
        assert mcp_line.split()[:2] == ["mcp", "unknown"]
        assert proc.returncode == 2


@needs_permissions
def test_a_project_dir_behind_an_unreadable_directory_is_not_a_traceback(
    tmp_path: Path, locked: Path
) -> None:
    via = tmp_path / "via"
    via.symlink_to(locked / "inner")
    proc = _run_doctor(tmp_path, "--project-dir", str(via))
    stderr = proc.stderr.decode(errors="replace")
    assert "Traceback" not in stderr, stderr
    assert "nothing was inspected" in stderr
    assert proc.returncode == 2


def test_doctor_leaves_the_process_streams_as_it_found_them(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The output is confined while `doctor` writes and restored afterwards —
    `SystemExit` included — so an in-process caller is not left with ASCII."""
    monkeypatch.setattr(doctor.shutil, "which", lambda *_, **__: None)
    before = [(s.encoding, s.errors) for s in (sys.stdout, sys.stderr)]
    with pytest.raises(SystemExit):
        cli.main(["doctor", "--project-dir", str(project)])
    assert [(s.encoding, s.errors) for s in (sys.stdout, sys.stderr)] == before
