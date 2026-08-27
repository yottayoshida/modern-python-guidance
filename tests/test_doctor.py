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

import os
import subprocess
from pathlib import Path

import pytest

from modern_python_guidance import doctor
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

    def test_a_group_without_a_command_is_degraded(self, project: Path) -> None:
        (project / ".claude" / "settings.local.json").write_text(
            '{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks":'
            ' [{"type": "command", "args": ["claude-post-tool-use"]}]}]}}'
        )
        report = diagnose_hook(project)
        assert report.state == DEGRADED
        assert "no usable command" in report.detail


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
