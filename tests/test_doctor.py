"""What `mpg doctor` reports, and what it exits with.

Three checks carry the weight, and each is written so that a plausible wrong
implementation fails it:

1. Every way a channel breaks is synthesised and the verdict is read back —
   with a healthy control in the same test, so neither "always degraded" nor
   "always healthy" survives.
2. The channel names are read out of a real run rather than compared to another
   constant. A table listing four channels and a loop visiting three satisfies
   a constant-to-constant check and fails this one.
3. `summarize([])` is 2. A run that measured nothing must not report health.
"""

from __future__ import annotations

import importlib.resources
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modern_python_guidance import __version__, doctor, setup_cmd
from modern_python_guidance.cli import main as cli_main
from modern_python_guidance.doctor import (
    ABSENT,
    CHANNELS,
    DEGRADED,
    PRESENT,
    UNKNOWN,
    ChannelReport,
    diagnose_all,
    diagnose_hook,
    diagnose_mcp,
    diagnose_rules,
    diagnose_skills,
    summarize,
)
from modern_python_guidance.setup_cmd import LINK_STALE, link_state

# Captured from a live `claude mcp get mpg` (2026-08-16), trimmed to the lines
# the parser reads. Kept verbatim rather than hand-written so the check-mark and
# the "Key: Value" spacing are the real ones — a parser tuned to a paraphrase
# would pass here and fail against the tool.
MCP_CONNECTED = (
    "mpg:\n"
    "  Scope: User config (available in all your projects)\n"
    "  Status: ✔ Connected\n"
    "  Type: stdio\n"
    "  Command: /opt/mpg/bin/python3\n"
    "  Args: -m modern_python_guidance mcp\n"
    "  Environment:\n"
    "\n"
    "To remove this server, run: claude mcp remove mpg -s user\n"
).encode()

MCP_FAILED = MCP_CONNECTED.replace(b"\xe2\x9c\x94 Connected", b"\xe2\x9c\x98 Failed to connect")
MCP_NO_STATUS = b"mpg:\n  Scope: User config\n  Type: stdio\n"

# Also captured live (2026-08-16), and captured from the right stream: asking
# about an unregistered server writes this to **stderr** and exits 1, with
# stdout empty. The distinction is the whole point of the check that reads it —
# looking at stdout would find nothing and fall through to `unknown` forever.
MCP_NOT_REGISTERED = b'No MCP server named "mpg". Configured servers: deepwiki, notion'


def _completed(
    stdout: bytes, returncode: int = 0, stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _install_skills(at: Path) -> Path:
    """A skills directory with something in it.

    The `SKILL.md` is not decoration. This fixture used to make a bare
    directory, and every skills assertion in this file was therefore written
    against an installation that delivers nothing — the exact false positive
    `_skills_are_delivered` exists to catch. Keeping the fixture empty and
    loosening the predicate would have been the other way to make these tests
    pass, and would have deleted the check instead of satisfying it.
    """
    at.mkdir(parents=True)
    (at / "SKILL.md").write_text("---\nname: modern-python-guidance\n---\n")
    return at


@pytest.fixture
def bundled(tmp_path: Path) -> tuple[Path, Path]:
    """A stand-in for the packaged skills directory and rule file."""
    skills = _install_skills(tmp_path / "installed" / "skills" / "modern-python-guidance")
    rule = tmp_path / "installed" / "rules" / "modern-python.md"
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text("---\npaths: []\n---\n")
    return skills, rule


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".claude").mkdir(parents=True)
    return root


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch, bundled: tuple[Path, Path]) -> tuple[Path, Path]:
    """Point doctor's notion of "the bundled source" at the fixture."""
    skills, rule = bundled
    monkeypatch.setattr(doctor, "_find_skills_dir", lambda: skills)
    monkeypatch.setattr(doctor, "_find_rule_source", lambda: rule)
    return skills, rule


def _link_skills(project: Path, target: Path) -> Path:
    path = project / ".claude" / "skills" / "modern-python-guidance"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target, target_is_directory=True)
    return path


def _link_rule(project: Path, target: Path) -> Path:
    path = project / ".claude" / "rules" / "modern-python.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)
    return path


def _recording_interpreter(directory: Path, marker: Path) -> Path:
    """A fake interpreter that records having been run, then answers correctly.

    It prints what a healthy `--version` prints, so a probe reaching it reads as
    `present` — the marker distinguishes "was not run" from "was run and
    failed", which a verdict alone cannot.
    """
    script = directory / "recording-interpreter.sh"
    script.write_text(f'#!/bin/sh\n: > "{marker}"\necho "modern-python-guidance {__version__}"\n')
    script.chmod(0o755)
    return script


def _survivors(script: Path) -> list[str]:
    """Processes still running this script, by name.

    The probe's contract is that a timed-out child does not outlive the answer.
    Asserting on the report alone cannot see that: a version of this code
    returned `unknown` on time and left `sleep` running for a day.
    """
    listing = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=False
    )
    return [line for line in listing.stdout.splitlines() if str(script) in line]


def _run_cli_doctor(project: Path, *flags: str) -> int:
    """Run the doctor CLI in-process and return its exit status."""
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["doctor", "--project-dir", str(project), *flags])
    return int(excinfo.value.code or 0)


def _write_hook(project: Path, command: str) -> None:
    settings = project / ".claude" / "settings.local.json"
    settings.write_text(
        '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command",'
        f' "command": "{command}", "args": ["-m", "modern_python_guidance", "hook",'
        ' "claude-post-tool-use"]}]}]}}'
    )


class TestSkillsAndRules:
    """The two symlink channels. Same predicate, so they are checked together."""

    def test_a_link_to_the_bundled_source_is_present(
        self, project: Path, sources: tuple[Path, Path]
    ) -> None:
        skills, rule = sources
        _link_skills(project, skills)
        _link_rule(project, rule)
        assert diagnose_skills(project).state == PRESENT
        assert diagnose_rules(project).state == PRESENT

    def test_a_link_into_another_live_installation_is_present(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """The false positive this command had for exactly one run.

        A user who installs mpg with uv and runs `doctor` out of a source
        checkout has links pointing at the uv installation, not at the checkout.
        Judging that as broken would make the verdict depend on which
        interpreter invoked doctor — measured against a real workspace, where
        both links were reported degraded while being perfectly healthy.
        """
        other = _install_skills(tmp_path / "other-install" / "skills" / "modern-python-guidance")
        _link_skills(project, other)
        report = diagnose_skills(project)
        assert report.state == PRESENT
        assert "different mpg installation" in report.detail

    def test_a_link_to_something_that_is_not_an_mpg_asset_is_degraded(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Existing is not the same as being another installation of mpg.

        The first version of this branch accepted any link whose target
        existed and told the reader it led to "a different mpg installation" —
        an assertion made from a test that never looked. A rule symlink
        repointed at an unrelated file is one of the decays this module's own
        docstring lists, and it was being reported as healthy.
        """
        unrelated = tmp_path / "unrelated" / "notes.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("nothing to do with mpg\n")
        _link_rule(project, unrelated)
        report = diagnose_rules(project)
        assert report.state == DEGRADED
        assert "not an mpg file" in report.detail

    def test_a_dangling_link_is_degraded(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path
    ) -> None:
        _link_skills(project, tmp_path / "gone" / "never-existed")
        report = diagnose_skills(project)
        assert report.state == DEGRADED
        assert "does not exist" in report.detail
        assert report.fix

    def test_a_flattened_link_is_degraded(self, project: Path, sources: tuple[Path, Path]) -> None:
        """The rule frozen as a real file — the shape that cost 2.5 months."""
        path = project / ".claude" / "rules" / "modern-python.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a real file, not a symlink\n")
        report = diagnose_rules(project)
        assert report.state == DEGRADED
        assert "not a symlink" in report.detail
        assert report.fix

    def test_nothing_there_is_absent(self, project: Path, sources: tuple[Path, Path]) -> None:
        assert diagnose_skills(project).state == ABSENT
        assert diagnose_rules(project).state == ABSENT

    def test_a_missing_bundled_source_is_unknown(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def missing() -> Path:
            raise FileNotFoundError("Cannot locate bundled skills directory")

        monkeypatch.setattr(doctor, "_find_skills_dir", missing)
        monkeypatch.setattr(doctor, "_find_rule_source", missing)
        assert diagnose_skills(project).state == UNKNOWN
        assert diagnose_rules(project).state == UNKNOWN

    def test_an_empty_target_is_degraded_on_both_paths_to_present(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """A link can be perfectly formed and deliver nothing.

        There are two ways to reach `present`, and both used to accept a target
        nobody had opened: a link to the bundled source, which is accepted on
        `is_dir()` / `is_file()`, and a link into another installation, accepted
        on the final path component alone. Named separately here because an
        implementation that guards only one of them passes half of this test —
        which is what the first draft of this change did.

        The healthy half is in the same test so that a predicate stuck at
        "always degraded" cannot pass either.
        """
        skills, rule = sources
        # --- the bundled source itself is hollow (`LINK_LINKED`)
        (skills / "SKILL.md").unlink()
        rule.write_text("")
        _link_skills(project, skills)
        _link_rule(project, rule)
        assert diagnose_skills(project).state == DEGRADED
        assert diagnose_rules(project).state == DEGRADED

        # --- another installation, right name, nothing behind it (`LINK_STALE`)
        hollow = tmp_path / "hollow-install" / "skills" / "modern-python-guidance"
        hollow.mkdir(parents=True)
        (project / ".claude" / "skills" / "modern-python-guidance").unlink()
        _link_skills(project, hollow)
        report = diagnose_skills(project)
        assert report.state == DEGRADED
        assert "no readable" in report.detail

        # --- control: the same two shapes, with content
        (skills / "SKILL.md").write_text("---\nname: modern-python-guidance\n---\n")
        rule.write_text("---\npaths: []\n---\n")
        (project / ".claude" / "skills" / "modern-python-guidance").unlink()
        _link_skills(project, skills)
        assert diagnose_skills(project).state == PRESENT
        assert diagnose_rules(project).state == PRESENT

        (skills / "SKILL.md").write_text("x")
        (project / ".claude" / "skills" / "modern-python-guidance").unlink()
        live = _install_skills(tmp_path / "live-install" / "modern-python-guidance")
        _link_skills(project, live)
        assert diagnose_skills(project).state == PRESENT

    def test_a_readlink_failure_reaches_neither_caller(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path, monkeypatch
    ) -> None:
        """The tree can move between the two reads of the same link.

        `link_state` classifies a link, then `_link_report` reads its
        destination again for the wording. Both calls used to be able to raise
        into the caller, and `link_state`'s docstring promised otherwise. A
        read-only diagnostic that tracebacks because a link vanished mid-run has
        failed at its only job.

        `os.readlink` itself is replaced, not `setup_cmd`'s binding, because the
        second read goes through `Path.readlink` in `doctor`. Patching one
        module's name would leave that call site untested — and an
        implementation that fixed only `link_state` would pass.
        """
        skills, _ = sources
        link = _link_skills(project, tmp_path / "elsewhere" / "modern-python-guidance")

        def vanished(*args: object, **kwargs: object) -> str:
            raise OSError("the link is gone")

        monkeypatch.setattr(os, "readlink", vanished)
        assert link_state(link, skills) == LINK_STALE
        report = diagnose_skills(project)  # must not raise
        assert report.state == DEGRADED


class TestHollowBundledSourceStaysMeasurable:
    """#238, pinned from doctor's side: the locators stay shape-only.

    `mpg setup` now refuses to link a hollow bundled source, and the rejected
    way to build that was a content predicate inside `_find_skills_dir`. That
    design turns this exact case into `unknown` ("cannot locate") — a measured
    breakage reported as an unmeasured one, doctor's exit flipped from 1 to 2,
    and README's "nothing behind it is `degraded`" promise unreachable.
    Reverting to it fails here.

    Unlike the `sources` fixture, nothing is monkeypatched between doctor and
    the locator: the real `_find_skills_dir` walks its dev fallback into this
    layout, so a predicate added to the locator itself is caught.
    """

    def _point_dev_fallback_at(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        # The importlib candidate is refused explicitly — with FileNotFoundError,
        # one of the two exceptions the locator's own `except` names — rather
        # than trusted to lose on its own. Under an editable install it would
        # (the package directory carries no skills/), but a wheel-installed
        # environment bundles real skills there, and this test must not pick
        # those up. Only the path arithmetic in `_find_skills_dir` reads
        # __file__; the file itself never has to exist.
        def refuse(_pkg: str) -> Path:
            raise FileNotFoundError("package resources disabled for this test")

        monkeypatch.setattr(importlib.resources, "files", refuse)
        fake_file = tmp_path / "src" / "modern_python_guidance" / "setup_cmd.py"
        monkeypatch.setattr(setup_cmd, "__file__", str(fake_file))
        skills = tmp_path / "skills" / "modern-python-guidance"
        skills.mkdir(parents=True)
        return skills

    def test_a_hollow_install_reads_degraded_not_unknown(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, tmp_path: Path
    ) -> None:
        skills = self._point_dev_fallback_at(monkeypatch, tmp_path)
        (skills / "SKILL.md").touch()  # present and empty: the packaging accident

        located = setup_cmd._find_skills_dir()
        assert located == skills  # still handed to doctor, not refused

        _link_skills(project, skills)
        report = diagnose_skills(project)
        assert report.state == DEGRADED
        assert "nothing behind it" in report.detail

    def test_the_same_layout_with_content_reads_present(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, tmp_path: Path
    ) -> None:
        """The healthy control, through the same unpatched locator."""
        skills = self._point_dev_fallback_at(monkeypatch, tmp_path)
        (skills / "SKILL.md").write_text("---\nname: modern-python-guidance\n---\n")

        _link_skills(project, skills)
        assert diagnose_skills(project).state == PRESENT


class TestHook:
    def test_a_registered_and_existing_interpreter_is_present(self, project: Path) -> None:
        _write_hook(project, "/usr/bin/env")
        report = diagnose_hook(project)
        assert report.state == PRESENT

    def test_no_settings_file_is_absent(self, project: Path) -> None:
        report = diagnose_hook(project)
        assert report.state == ABSENT
        assert report.fix

    def test_settings_without_an_mpg_group_is_absent(self, project: Path) -> None:
        (project / ".claude" / "settings.local.json").write_text('{"hooks": {"PostToolUse": []}}')
        assert diagnose_hook(project).state == ABSENT

    def test_unreadable_settings_is_degraded_not_unknown(self, project: Path) -> None:
        """`read_settings` fails closed on four shapes; all four are breakage.

        The file is there and mpg cannot read it — something the user can act
        on, which is what separates `degraded` from `unknown` here.
        """
        (project / ".claude" / "settings.local.json").write_text("{ not json")
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert report.fix

    def test_a_hook_pinned_to_a_throwaway_interpreter_is_degraded(self, project: Path) -> None:
        _write_hook(project, "/tmp/uvx-cache-abc123/bin/python")
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "throwaway" in report.detail

    def test_a_hook_whose_binary_is_gone_is_degraded(self, project: Path) -> None:
        _write_hook(project, "/opt/removed-venv/bin/python3")
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "does not exist" in report.detail

    def test_a_foreign_entry_in_the_same_group_is_not_the_one_judged(self, project: Path) -> None:
        """`find_mpg_group` returns the group, not the entry.

        A PostToolUse group may legitimately hold mpg's entry alongside another
        tool's — `hook_config._strip_mpg_entries` exists to preserve exactly
        that shape — so taking the first entry means judging somebody else's
        hook and reporting their binary as mpg's. The foreign entry is placed
        first here so that "first entry" and "mpg's entry" cannot coincide.
        """
        (project / ".claude" / "settings.local.json").write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            '{"type": "command", "command": "/nonexistent/somebody-elses-tool.sh"},'
            '{"type": "command", "command": "/usr/bin/env", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == PRESENT
        assert "somebody-elses-tool" not in report.detail

    def test_the_legacy_shell_string_form_is_named_rather_than_called_missing(
        self, project: Path
    ) -> None:
        """The form README used to document, and `_is_mpg_entry` still accepts.

        There `command` holds the whole invocation as a shell string, not an
        interpreter path. Everything after this check treats it as a path, so
        without this branch `Path(...).exists()` states that `mpg hook
        claude-post-tool-use` "does not exist" — about a string that may well
        resolve on PATH. Old, drifted installs are this command's entire
        population, so it is precisely what it will meet.
        """
        (project / ".claude" / "settings.local.json").write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            '{"type": "command", "command": "mpg hook claude-post-tool-use"}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "legacy" in report.detail
        assert "does not exist" not in report.detail

    def test_what_fires_is_counted_per_tool_not_per_group(self, project: Path) -> None:
        """A registration can be well formed and never run, or run twice.

        Three shapes in one test, because each of them is what a different wrong
        implementation gets right:

        (a) a matcher that names another tool. The entry is exactly what setup
            writes; it simply never sees an edit. Nothing looked at `matcher`
            before, so this read `present`.
        (b) two mpg entries inside one group. Counting groups finds one and
            calls it healthy — the shape `merge_hook` exists to converge, seen
            by the reader as a single registration.
        (c) `Edit` and `Write` split across two groups. This is the control:
            counting groups calls it a duplicate, when between them they cover
            exactly what mpg's own matcher covers.
        """
        canonical = (
            '{"type": "command", "command": "/usr/bin/env", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}'
        )
        settings = project / ".claude" / "settings.local.json"

        settings.write_text(
            f'{{"hooks": {{"PostToolUse": [{{"matcher": "Bash", "hooks": [{canonical}]}}]}}}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "no entry's matcher selects" in report.detail

        settings.write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            f"{canonical}, {canonical}]}}]}}}}"
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "2 mpg hook entries" in report.detail

        settings.write_text(
            '{"hooks": {"PostToolUse": ['
            f'{{"matcher": "Edit", "hooks": [{canonical}]}},'
            f'{{"matcher": "Write", "hooks": [{canonical}]}}]}}}}'
        )
        assert diagnose_hook(project).state == PRESENT

    def test_an_entry_that_will_not_invoke_mpg_is_degraded(self, project: Path) -> None:
        """`_is_mpg_entry` answers "is this ours", not "will this invoke us".

        It matches on the subcommand token appearing anywhere in `args`, which
        is the right test for ownership and no test at all for the invocation.
        An entry can carry that token, be found, and run something else.
        """
        settings = project / ".claude" / "settings.local.json"
        settings.write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            '{"type": "command", "command": "/usr/bin/env", "args": ["-m",'
            ' "some_other_module", "hook", "claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "some_other_module" in report.detail

        settings.write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            '{"type": "prompt", "command": "/usr/bin/env", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "prompt" in report.detail

    def test_a_command_that_cannot_be_spawned_is_degraded(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing is not the same as being runnable.

        `Path("/").exists()` is True, and so is a text file's. Claude Code can
        spawn neither, so the check that only asked whether the path existed
        was reporting `present` about a hook that cannot start — the shape of
        false positive the rest of this change is about.
        """
        _write_hook(project, "/")
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "not a file" in report.detail

        # pytest's tmp dir sits under a system temp root, which the ephemeral
        # check answers first. That check has its own test above; silencing it
        # here isolates the execute bit rather than removing anything.
        monkeypatch.setattr(doctor, "is_ephemeral_interpreter", lambda _: False)
        not_executable = project / "plain.txt"
        not_executable.write_text("#!/bin/sh\n")
        _write_hook(project, str(not_executable))
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "not executable" in report.detail

    def test_a_hollow_check_does_not_block_on_a_fifo(
        self, project: Path, sources: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Opening `SKILL.md` must not hand control to whoever wrote the tree.

        A skills directory lives in a repository, so `SKILL.md` can be a symlink
        to a fifo and arrive by `git clone`. A blocking `open()` on it stops
        `mpg doctor` — the command someone runs *because* they do not trust the
        state of the tree — until the process is killed. If this test ever hangs
        rather than fails, that is the bug.
        """
        install = tmp_path / "fifo-install" / "modern-python-guidance"
        install.mkdir(parents=True)
        os.mkfifo(install / "SKILL.md")
        _link_skills(project, install)
        report = diagnose_skills(project)
        assert report.state == DEGRADED
        assert "no readable" in report.detail

    def test_a_certain_duplicate_survives_an_unevaluable_matcher(self, project: Path) -> None:
        """What one entry hides must not erase what the others showed.

        Two canonical entries are a duplicate whatever a third turns out to be.
        Folding the whole tool into `unknown` on the first thing it could not
        read threw away a determined verdict — and its fix — in favour of a
        report that tells the reader nothing to do.
        """
        canonical = (
            '{"type": "command", "command": "/bin/sh", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}'
        )
        settings = project / ".claude" / "settings.local.json"
        settings.write_text(
            '{"hooks": {"PostToolUse": ['
            f'{{"matcher": "Edit|Write", "hooks": [{canonical}, {canonical}]}},'
            f'{{"matcher": "Edit(", "hooks": [{canonical}]}}]}}}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "2 mpg hook entries" in report.detail
        assert report.fix

    def test_a_matcher_this_cannot_evaluate_is_unknown_not_degraded(self, project: Path) -> None:
        """Claude Code evaluates the regex form in JavaScript.

        Python's `re` is a different language at the edges, so a pattern it
        refuses is one this process has not measured — not one Claude Code
        cannot run. Calling it degraded would report a healthy registration as
        broken on the strength of a check that never completed.
        """
        settings = project / ".claude" / "settings.local.json"
        settings.write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit(", "hooks": ['
            '{"type": "command", "command": "/usr/bin/env", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == UNKNOWN
        assert "not established" in report.detail

    def test_a_matcher_only_one_engine_accepts_is_unknown_through_the_whole_channel(
        self, project: Path
    ) -> None:
        """#237, end to end rather than at `matcher_fires_on`.

        `(?P<x>Edit)|Write` compiles in Python and selects both tools; in
        JavaScript, where Claude Code evaluates it, named groups are
        `(?<x>...)` and this is a syntax error — so the hook never runs. The
        channel used to read `present` for it, which is the silent wrong answer
        this whole check exists to stop. Written through `diagnose_hook` because
        the unit test cannot show that the verdict survives to the channel.
        """
        settings = project / ".claude" / "settings.local.json"
        settings.write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "(?P<x>Edit)|Write", "hooks": ['
            '{"type": "command", "command": "/usr/bin/env", "args": ["-m",'
            ' "modern_python_guidance", "hook", "claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == UNKNOWN
        assert "not established" in report.detail
        # An unevaluable matcher leaves the reader with no `fix` by design, so
        # the one thing they can still do belongs in the detail. Without this
        # the channel says a hook may not be reaching them and stops there.
        assert "--with-hook" in report.detail
        assert not report.fix

    def test_a_group_without_a_command_is_degraded(self, project: Path) -> None:
        (project / ".claude" / "settings.local.json").write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks":'
            ' [{"type": "command", "args": ["claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "no usable command" in report.detail


class TestProbeTheRegisteredInterpreter:
    """#236: the opt-in check that runs the interpreter a settings file names.

    Its own class because every test here has to silence the ephemeral-path
    check first. `tmp_path` is derived from `tempfile.gettempdir()`, which is
    `/tmp` on Linux and resolves under `/private/var/folders` on macOS —
    both of them roots `is_ephemeral_interpreter` rejects. Left alone, every
    probe test would be answered `degraded` by the shape checks and pass
    without the probe ever running, on either platform.

    Silencing it here isolates the probe; the ephemeral check keeps its own
    tests in the class above.
    """

    @pytest.fixture(autouse=True)
    def _allow_temp_interpreters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(doctor, "is_ephemeral_interpreter", lambda _: False)

    def test_a_probe_is_not_run_unless_asked_for(self, project: Path, tmp_path: Path) -> None:
        """#236: the default is the security boundary, so measure it from outside.

        A script that records having run, registered as the interpreter. Without
        the flag the marker must not appear — checked through `diagnose_hook`
        *and* through `main(["doctor"])`, because a default of False in the
        function still executes if the CLI passes True unconditionally, and
        neither test catches the other's mutation.

        The marker path is absolute: the probe runs with a cut-down environment in
        a scratch directory, so a relative one would land somewhere this test
        cannot see and the assertion would pass for the wrong reason.
        """
        marker = tmp_path / "probe-ran"
        interpreter = _recording_interpreter(tmp_path, marker)
        _write_hook(project, str(interpreter))

        assert diagnose_hook(project).state == PRESENT
        assert not marker.exists(), "diagnose_hook ran the interpreter without being asked"

        exit_code = _run_cli_doctor(project)
        assert not marker.exists(), "the doctor CLI ran the interpreter without --run-interpreter"
        assert exit_code == 0

        # The positive control: the same registration, asked to probe, does run
        # it. Without this the assertions above pass for an implementation that
        # can never probe at all.
        _run_cli_doctor(project, "--run-interpreter")
        assert marker.exists(), "--run-interpreter did not reach the interpreter"

    def test_an_interpreter_without_mpg_is_degraded_even_when_it_succeeds(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Exit status is not the test — measured, not assumed.

        A script that ignores its arguments and exits 0 passes every shape check
        and every exit-status probe, while loading nothing. Comparing the output
        against what `--version` prints is what separates it from a real
        interpreter, and this test fails if that comparison is dropped.
        """
        liar = tmp_path / "liar.sh"
        liar.write_text("#!/bin/sh\nexit 0\n")
        liar.chmod(0o755)
        _write_hook(project, str(liar))

        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == DEGRADED
        assert "without printing mpg's version" in report.detail

    def test_a_real_interpreter_with_mpg_is_present(self, project: Path) -> None:
        """The healthy control for the two tests around it: a probe that answers
        correctly still reads `present`, so neither "always degraded" nor a
        comparison against the wrong string survives."""
        _write_hook(project, sys.executable)
        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == PRESENT, report.detail
        assert __version__ in report.detail

    def test_what_the_cli_prints_is_what_the_probe_recognises(self) -> None:
        """Two definitions of one string, held together.

        `doctor` recognises `modern-python-guidance <version>`; the CLI prints
        argparse's `prog` and the package version. If either moves, every
        healthy installation reads as degraded — a failure that would look like
        a broken environment rather than a broken constant. Run through the same
        argv the probe uses, so a change to that shape is caught here too.
        """
        proc = subprocess.run(
            doctor._probe_command(sys.executable),
            capture_output=True,
            text=True,
            check=True,
        )
        assert doctor._version_from_probe_output(proc.stdout.strip()) == __version__

    def test_a_broken_shebang_is_degraded_not_unknown(self, project: Path, tmp_path: Path) -> None:
        """Failing to start is not the same as failing to measure.

        A script whose interpreter does not exist passes exists/is_file/X_OK and
        then fails at exec. Claude Code spawning the same hook hits the same
        wall, so this is a measured failure — `degraded`, exit 1 — not an
        unmeasured one. Folding it into `unknown` would exit 2 and tell the
        reader nothing was established, when in fact something was.
        """
        broken = tmp_path / "broken.sh"
        broken.write_text("#!/nonexistent-interpreter\nexit 0\n")
        broken.chmod(0o755)
        _write_hook(project, str(broken))

        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == DEGRADED
        assert "cannot be executed" in report.detail
        assert report.fix

    def test_a_child_that_escapes_the_process_group_cannot_hang_the_probe(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The probe must return even when the killing does not work.

        `start_new_session` puts the child in its own process group and the
        timeout kills the group — but a child that calls `setsid()` itself and
        leaves a grandchild holding stdout escapes it. Draining the pipe after
        that waits for an EOF that never comes, and `mpg doctor
        --run-interpreter` hangs with no message at all. Found by review, with
        this shape; if this test hangs rather than fails, it is back.

        The grandchild outlives the test by design, so it is given a short life
        of its own rather than relying on being killed.
        """
        monkeypatch.setattr(doctor, "PROBE_TIMEOUT_SECONDS", 0.5)
        escaper = tmp_path / "escaper.sh"
        escaper.write_text(
            "#!/bin/sh\n"
            f'{sys.executable} -c "import os,time; os.setsid(); time.sleep(20)" &\n'
            "sleep 20\n"
        )
        escaper.chmod(0o755)
        _write_hook(project, str(escaper))

        started = time.monotonic()
        report = diagnose_hook(project, run_interpreter=True)
        elapsed = time.monotonic() - started

        assert report.state == UNKNOWN
        assert "did not answer" in report.detail
        assert elapsed < 10, f"the probe took {elapsed:.1f}s — it waited on the escaped child"
        # Returning on time is only half of it. The first fix did that and left
        # the child running, because the early return jumped over the kill.
        assert not _survivors(escaper), "the probe returned but left its direct child alive"

    def test_a_chatty_interpreter_cannot_exhaust_memory(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Output is read up to a limit, not to EOF.

        `cat /dev/zero` as the registered command took this process to 2.3 GB
        resident in one second when the pipe was drained without a bound
        (measured in review). The check needs about thirty bytes.
        """
        monkeypatch.setattr(doctor, "PROBE_TIMEOUT_SECONDS", 0.5)
        monkeypatch.setattr(doctor, "PROBE_OUTPUT_LIMIT", 256)
        firehose = tmp_path / "firehose.sh"
        firehose.write_text("#!/bin/sh\nexec cat /dev/zero\n")
        firehose.chmod(0o755)
        _write_hook(project, str(firehose))

        captured: list[bytes] = []
        real_read = doctor._read_bounded

        def recording(proc: subprocess.Popen[bytes]) -> doctor._ProbeOutput:
            output = real_read(proc)
            captured.append(output.data)
            return output

        monkeypatch.setattr(doctor, "_read_bounded", recording)
        report = diagnose_hook(project, run_interpreter=True)

        assert captured, "the probe never read the child's output"
        assert len(captured[0]) <= 256, f"read {len(captured[0])} bytes past the limit"
        assert report.state in {DEGRADED, UNKNOWN}

    def test_an_older_mpg_in_the_hook_interpreter_is_still_present(
        self, project: Path, tmp_path: Path
    ) -> None:
        """A hook wired to a different mpg version is working, not broken.

        Comparing the probe's output against *this* process's `__version__`
        would report an interpreter holding mpg 1.0.9 as "not an interpreter
        with mpg installed" — false, and the same mistake `_link_report` avoids
        for a link into another installation.
        """
        older = tmp_path / "older-mpg.sh"
        older.write_text('#!/bin/sh\necho "modern-python-guidance 0.0.1-not-this-one"\n')
        older.chmod(0o755)
        _write_hook(project, str(older))

        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == PRESENT, report.detail
        assert "0.0.1-not-this-one" in report.detail

    def test_output_that_only_resembles_a_version_is_not_accepted(
        self, project: Path, tmp_path: Path
    ) -> None:
        """The control for the test above: accepting any version must not become
        accepting any output. A bare echo of the program name is not a version,
        and neither is a sentence that happens to start with it."""
        for script_body in (
            'echo "modern-python-guidance"\n',
            'echo "modern-python-guidance is not installed here"\n',
            'echo "something-else 1.1.0"\n',
        ):
            impostor = tmp_path / "impostor.sh"
            impostor.write_text(f"#!/bin/sh\n{script_body}")
            impostor.chmod(0o755)
            _write_hook(project, str(impostor))

            report = diagnose_hook(project, run_interpreter=True)
            assert report.state == DEGRADED, f"{script_body!r} was accepted: {report.detail}"

    def test_an_interpreter_that_never_answers_is_unknown(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other half of the classification, and the timeout path itself.

        The timeout is shortened rather than waited out; what is being checked
        is that a child which outlives it is killed and reported as unmeasured,
        not how long five seconds is.
        """
        monkeypatch.setattr(doctor, "PROBE_TIMEOUT_SECONDS", 0.3)
        sleeper = tmp_path / "sleeper.sh"
        sleeper.write_text("#!/bin/sh\nsleep 30\n")
        sleeper.chmod(0o755)
        _write_hook(project, str(sleeper))

        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == UNKNOWN
        assert "did not answer" in report.detail
        assert not _survivors(sleeper), "the timed-out child outlived the answer"

    def test_the_child_gets_only_path_and_home(self, project: Path, tmp_path: Path) -> None:
        """What the probe hands the child, measured from the child.

        The bounds this feature is argued from are listed in the README, and one
        of them is the environment. When it went from empty to `PATH` and `HOME`
        — so pyenv and conda shims could start — four prose descriptions of it
        stayed behind, because nothing here read the value. This is that reader.
        """
        dump = tmp_path / "env-dump"
        reporter = tmp_path / "report-env.sh"
        reporter.write_text(f'#!/bin/sh\nenv > "{dump}"\necho "modern-python-guidance 1.0"\n')
        reporter.chmod(0o755)
        _write_hook(project, str(reporter))

        assert diagnose_hook(project, run_interpreter=True).state == PRESENT
        seen = {line.split("=", 1)[0] for line in dump.read_text().splitlines() if "=" in line}
        # `_` and `PWD` are set by the shell itself, not inherited.
        assert seen - {"_", "PWD", "SHLVL"} == {"PATH", "HOME"}, sorted(seen)

    def test_at_most_four_interpreters_are_actually_run(
        self, project: Path, tmp_path: Path
    ) -> None:
        """The limit is on executions, not on the wording of a report.

        Six distinct commands, each recording that it ran: exactly four markers
        must appear. Counting the report's sentences instead would pass for an
        implementation that runs all six and mentions four.
        """
        entries = []
        markers = []
        for index in range(6):
            marker = tmp_path / f"ran-{index}"
            markers.append(marker)
            script = tmp_path / f"interp-{index}.sh"
            script.write_text(f'#!/bin/sh\n: > "{marker}"\necho "modern-python-guidance 1.0"\n')
            script.chmod(0o755)
            entries.append(
                '{"type": "command", "command": "' + str(script) + '", "args": ["-m",'
                ' "modern_python_guidance", "hook", "claude-post-tool-use"]}'
            )
        (project / ".claude" / "settings.local.json").write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": ['
            + ", ".join(entries)
            + "]}]}}"
        )

        report = diagnose_hook(project, run_interpreter=True)
        assert sum(marker.exists() for marker in markers) == doctor.PROBE_LIMIT
        assert report.state == UNKNOWN
        assert "were not run" in report.detail

    def test_probe_output_cannot_forge_the_report(self, project: Path, tmp_path: Path) -> None:
        """The probe prints part of the child's output back to a terminal.

        A version accepted as "any token without spaces" let this through:

            modern-python-guidance 1.1.0\\x1b[2K\\rhook  present  registered and healthy

        `ESC [ 2K` erases the line and `\\r` returns to its start, so the child
        rewrites doctor's own verdict — from a settings file that, as the README
        says, may have arrived with a cloned repository. Found in review, with
        exactly this script.
        """
        esc = chr(27)
        forger = tmp_path / "forger.sh"
        forger.write_text(
            "#!/bin/sh\n"
            f"printf 'modern-python-guidance 1.1.0{esc}[2K\\rhook\\tpresent\\tall good\\n'\n"
        )
        forger.chmod(0o755)
        _write_hook(project, str(forger))

        report = diagnose_hook(project, run_interpreter=True)
        assert report.state == DEGRADED, report.detail
        assert esc not in report.detail
        assert "\r" not in report.detail


class TestMcp:
    def test_no_claude_on_path_is_absent_not_unknown(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without `claude`, `setup_mcp` cannot have registered anything.

        Calling this `unknown` would put exit 2 on every CI run — `ci.yml`
        installs Python and uv, never Claude Code — and make exit 0
        unreachable there.
        """
        monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
        report = diagnose_mcp(project)
        assert report.state == ABSENT
        assert report.fix

    def test_a_connected_registration_is_present(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor, "_run_claude_mcp_quiet", lambda *a, **k: _completed(MCP_CONNECTED)
        )
        report = diagnose_mcp(project)
        assert report.state == PRESENT
        # Reported, never judged: which command is registered is shown to the
        # reader but does not decide the verdict.
        assert "/opt/mpg/bin/python3" in report.detail

    def test_a_registration_that_does_not_connect_is_degraded(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor, "_run_claude_mcp_quiet", lambda *a, **k: _completed(MCP_FAILED)
        )
        report = diagnose_mcp(project)
        assert report.state == DEGRADED
        assert report.fix

    def test_an_unregistered_server_is_absent(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor,
            "_run_claude_mcp_quiet",
            lambda *a, **k: _completed(b"", returncode=1, stderr=MCP_NOT_REGISTERED),
        )
        assert diagnose_mcp(project).state == ABSENT

    def test_a_non_zero_exit_that_is_not_absence_is_unknown(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not every failure of `claude mcp get` means "nothing is registered".

        A corrupt config, a failed authorisation, and a crash all exit
        non-zero. Reading absence out of all of them would report `absent` —
        and, since absence is healthy, exit 0 — for a machine whose
        registration was never examined. That is the confusion this whole
        command exists to end, so it must not be committed here.
        """
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor,
            "_run_claude_mcp_quiet",
            lambda *a, **k: _completed(b"", returncode=2, stderr=b"config file is corrupt"),
        )
        report = diagnose_mcp(project)
        assert report.state == UNKNOWN
        assert "corrupt" in report.detail

    def test_a_command_that_did_not_complete_is_unknown(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(doctor, "_run_claude_mcp_quiet", lambda *a, **k: None)
        assert diagnose_mcp(project).state == UNKNOWN

    def test_output_without_a_status_line_is_unknown_not_present(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A changed output format must not read as health.

        `_effective_scope` answers an unreadable format with silence because a
        wrong warning there would send a user to delete a working registration.
        Here the stakes are reversed: staying silent would mean reporting a
        channel as fine without having established anything about it.
        """
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor, "_run_claude_mcp_quiet", lambda *a, **k: _completed(MCP_NO_STATUS)
        )
        assert diagnose_mcp(project).state == UNKNOWN

    def test_the_parser_keeps_a_missing_field_missing(self) -> None:
        fields = doctor._parse_mcp_fields(MCP_NO_STATUS)
        assert fields["Scope"] == "User config"
        assert "Status" not in fields

    def test_the_parser_reads_the_live_capture(self) -> None:
        fields = doctor._parse_mcp_fields(MCP_CONNECTED)
        assert "Connected" in fields["Status"]
        assert fields["Command"] == "/opt/mpg/bin/python3"
        assert fields["Args"] == "-m modern_python_guidance mcp"


class TestSummarize:
    def test_an_empty_report_set_is_not_healthy(self) -> None:
        """Check 3. A run that evaluated nothing has established nothing.

        Exit 0 here would make "everything is fine" indistinguishable from
        "nothing was measured" — the failure this command exists to catch,
        committed by the command itself.
        """
        assert summarize([]) == 2

    def test_degraded_beats_present_and_absent(self) -> None:
        assert (
            summarize(
                [
                    ChannelReport("a", PRESENT, ""),
                    ChannelReport("b", ABSENT, ""),
                    ChannelReport("c", DEGRADED, ""),
                ]
            )
            == 1
        )

    def test_unknown_beats_degraded(self) -> None:
        """Ordering matters: "could not tell" outranks "is broken".

        A run that could not evaluate a channel cannot claim to have found all
        the breakage, so its status says "look" rather than "one thing is wrong".
        """
        assert summarize([ChannelReport("a", DEGRADED, ""), ChannelReport("b", UNKNOWN, "")]) == 2

    def test_present_and_absent_together_are_healthy(self) -> None:
        """`--mcp-only` / `--skills-only` / `--no-hook` make absence a choice."""
        assert summarize([ChannelReport("a", PRESENT, ""), ChannelReport("b", ABSENT, "")]) == 0


class TestDiagnoseAll:
    def test_a_run_reports_every_channel_exactly_once(
        self, project: Path, sources: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Check 2. Read out of a real run rather than from a second constant.

        What this catches, measured by slicing the loop to three: a
        `diagnose_all` that iterates fewer entries than the table declares.

        What it does not catch, and the docstring said it did until a reviewer
        checked: a channel deleted from `CHANNELS` itself. `diagnose_all`
        iterates that same tuple, so both sides shrink together and the
        comparison still holds. The count of four is pinned by check 1's
        exact-dict comparison instead, which names the channels literally.
        """
        monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
        reported = [report.channel for report in diagnose_all(project)]
        assert reported == list(CHANNELS)
        assert len(reported) == len(set(reported))

    def test_every_breakage_is_found_and_a_healthy_tree_is_not(
        self,
        project: Path,
        sources: tuple[Path, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Check 1. Every shape that broke the real workspace, plus a control.

        The control is in the same test on purpose: without it, "always
        degraded" passes the breakage half, and without the breakage half,
        "always healthy" passes the control.

        Honest limit: three of the four are the real thing on disk — a
        flattened file, a dangling link, a missing hook. The MCP channel is
        stubbed, because the alternative is breaking the machine's actual
        registration. So the control's `present` for MCP is a statement about a
        fabricated world, and only the other three are measured end to end.
        """
        skills, rule = sources
        monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/local/bin/claude")

        # --- broken: every channel in a different failure mode
        monkeypatch.setattr(
            doctor, "_run_claude_mcp_quiet", lambda *a, **k: _completed(MCP_FAILED)
        )
        _link_skills(project, tmp_path / "gone")  # dangling
        flattened = project / ".claude" / "rules" / "modern-python.md"
        flattened.parent.mkdir(parents=True, exist_ok=True)
        flattened.write_text("frozen content\n")  # flattened
        # hook: nothing written at all

        broken = {report.channel: report.state for report in diagnose_all(project)}
        assert broken == {
            "mcp": DEGRADED,
            "skills": DEGRADED,
            "rules": DEGRADED,
            "hook": ABSENT,
        }
        assert summarize(diagnose_all(project)) == 1

        # --- control: the same tree, repaired
        monkeypatch.setattr(
            doctor, "_run_claude_mcp_quiet", lambda *a, **k: _completed(MCP_CONNECTED)
        )
        (project / ".claude" / "skills" / "modern-python-guidance").unlink()
        _link_skills(project, skills)
        flattened.unlink()
        _link_rule(project, rule)
        _write_hook(project, "/usr/bin/env")

        healthy = {report.channel: report.state for report in diagnose_all(project)}
        assert healthy == {
            "mcp": PRESENT,
            "skills": PRESENT,
            "rules": PRESENT,
            "hook": PRESENT,
        }
        assert summarize(diagnose_all(project)) == 0
