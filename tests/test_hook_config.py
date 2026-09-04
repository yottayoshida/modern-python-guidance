"""Tests for hook_config.py: settings.local.json PostToolUse merge/unmerge.

Case IDs (H1-H11, N1-N6, A1-A11) trace to the #152 PR2 shape enumeration:
`.claude/plans/sprightly-riding-globe-pr2-shapes.md`.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from modern_python_guidance import hook_config
from modern_python_guidance.hook_config import (
    HOOK_EVENT,
    HOOK_MATCHER,
    HOOK_TOOLS,
    HookConfigError,
    build_mpg_hook_entry,
    find_mpg_entries,
    find_mpg_group,
    has_mpg_hook,
    is_ephemeral_interpreter,
    matcher_fires_on,
    merge_hook,
    read_settings,
    settings_local_path,
    symlinked_parent_notes,
    unmerge_hook,
    write_settings_atomic,
)

PYTHON = "/Users/i.yoshida/claude_workspace/modern-python-guidance/.venv/bin/python3"


# --- real-shaped fixtures (from shape enumeration §1/§2) ---

H3_MODAL_PERMS_ONLY = {
    "permissions": {"allow": ["Bash(git *)"], "deny": []},
    "enableAllProjectMcpServers": False,
    "outputStyle": "explanatory",
}

H4_PRE_TOOL_USE_ONLY = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": 'tool == "Bash" && tool_input.command matches "--allow-dirty"',
                "hooks": [{"type": "command", "command": "#!/bin/bash\n...\nexit 2\n"}],
            }
        ]
    }
}

H5_FOREIGN_GROUPS_RICH = {
    "effortLevel": "high",
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "/abs/some-guard.sh"}],
                "x-omamori-version": "0.13.1",
            }
        ],
        "PostToolUse": [
            {
                "matcher": 'tool == "Edit" && tool_input.file_path matches "\\.(ts|tsx)$"',
                "hooks": [{"type": "command", "command": "#!/bin/bash\necho check\nexit 0\n"}],
            },
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "/abs/clawd-hook.sh",
                        "if": "Bash(npx *)",
                        "timeout": 10,
                    }
                ],
            },
        ],
        "SessionEnd": [{"hooks": [{"type": "command", "command": "/abs/cleanup.sh"}]}],
    },
    "permissions": {"allow": []},
    "statusLine": {"type": "command"},
}

H7_LEGACY_BARE = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Edit|Write",
                "hooks": [{"type": "command", "command": "mpg hook claude-post-tool-use"}],
            }
        ]
    }
}

N2_MATCHER_OMITTED_AND_WILDCARD = {
    "hooks": {
        "SessionEnd": [{"hooks": [{"type": "command", "command": "/abs/x.sh"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "/abs/y.sh"}]}],
    }
}


# --- pure function tests: merge_hook / unmerge_hook ---


class TestMergeHook:
    def test_h1_absent_creates_structure(self):
        """Covers H1 (absent) and H2 ({}) — both start merge_hook from an
        empty dict, so there is no distinct code path to exercise twice."""
        result = merge_hook({}, PYTHON)
        assert has_mpg_hook(result)
        group = find_mpg_group(result)
        assert group is not None
        assert group["matcher"] == "Edit|Write"
        assert group["hooks"][0]["command"] == PYTHON
        assert group["hooks"][0]["args"] == [
            "-m",
            "modern_python_guidance",
            "hook",
            "claude-post-tool-use",
        ]

    def test_h3_modal_preserves_siblings(self):
        result = merge_hook(H3_MODAL_PERMS_ONLY, PYTHON)
        assert result["permissions"] == H3_MODAL_PERMS_ONLY["permissions"]
        assert result["enableAllProjectMcpServers"] is False
        assert result["outputStyle"] == "explanatory"
        assert len(result["hooks"][HOOK_EVENT]) == 1

    def test_h3_does_not_mutate_input(self):
        original = json.loads(json.dumps(H3_MODAL_PERMS_ONLY))
        merge_hook(H3_MODAL_PERMS_ONLY, PYTHON)
        assert original == H3_MODAL_PERMS_ONLY

    def test_h4_preserves_pre_tool_use(self):
        result = merge_hook(H4_PRE_TOOL_USE_ONLY, PYTHON)
        assert result["hooks"]["PreToolUse"] == H4_PRE_TOOL_USE_ONLY["hooks"]["PreToolUse"]
        assert len(result["hooks"][HOOK_EVENT]) == 1

    def test_h5_appends_without_touching_foreign_groups(self):
        result = merge_hook(H5_FOREIGN_GROUPS_RICH, PYTHON)
        # foreign PreToolUse (with custom key) byte-stable
        assert result["hooks"]["PreToolUse"] == H5_FOREIGN_GROUPS_RICH["hooks"]["PreToolUse"]
        # foreign PostToolUse groups (dead matcher + if/timeout) byte-stable
        assert result["hooks"][HOOK_EVENT][0] == H5_FOREIGN_GROUPS_RICH["hooks"][HOOK_EVENT][0]
        assert result["hooks"][HOOK_EVENT][1] == H5_FOREIGN_GROUPS_RICH["hooks"][HOOK_EVENT][1]
        assert len(result["hooks"][HOOK_EVENT]) == 3
        assert find_mpg_group(result) is not None
        # sibling top-level keys + other events survive
        assert result["effortLevel"] == "high"
        assert result["statusLine"] == {"type": "command"}
        assert result["hooks"]["SessionEnd"] == H5_FOREIGN_GROUPS_RICH["hooks"]["SessionEnd"]

    def test_h6_idempotent_second_merge_is_byte_identical(self):
        first = merge_hook({}, PYTHON)
        second = merge_hook(first, PYTHON)
        assert first == second
        assert len(second["hooks"][HOOK_EVENT]) == 1

    def test_h7_legacy_bare_mpg_migrated_not_duplicated(self):
        result = merge_hook(H7_LEGACY_BARE, PYTHON)
        assert len(result["hooks"][HOOK_EVENT]) == 1
        assert result["hooks"][HOOK_EVENT][0]["hooks"][0]["command"] == PYTHON
        assert result["hooks"][HOOK_EVENT][0]["hooks"][0]["args"] == [
            "-m",
            "modern_python_guidance",
            "hook",
            "claude-post-tool-use",
        ]

    def test_a2_hooks_not_object_raises(self):
        with pytest.raises(HookConfigError, match="not a JSON object"):
            merge_hook({"hooks": []}, PYTHON)

    def test_a3_post_tool_use_not_array_raises(self):
        with pytest.raises(HookConfigError, match="not a JSON array"):
            merge_hook({"hooks": {HOOK_EVENT: "oops"}}, PYTHON)

    def test_a4_group_not_object_skipped_defensively(self):
        """A malformed foreign group (string/null/list) must not crash the
        scan; it's simply not recognized as mpg's and mpg still appends."""
        settings = {"hooks": {HOOK_EVENT: [None, "oops", ["nested"]]}}
        result = merge_hook(settings, PYTHON)
        assert len(result["hooks"][HOOK_EVENT]) == 4
        assert find_mpg_group(result) is not None

    def test_a5_entry_without_command_does_not_crash(self):
        settings = {"hooks": {HOOK_EVENT: [{"matcher": "Bash", "hooks": [{"type": "command"}]}]}}
        result = merge_hook(settings, PYTHON)
        # foreign command-less entry preserved, mpg appended separately
        assert len(result["hooks"][HOOK_EVENT]) == 2

    def test_group_hooks_not_a_list_does_not_crash(self):
        """Round1 P2 mutation-survival gap: a group whose `hooks` field is
        itself malformed (not a list) must not crash the scan and must not
        be misidentified as mpg's own."""
        settings = {"hooks": {HOOK_EVENT: [{"matcher": "Bash", "hooks": "not-a-list"}]}}
        result = merge_hook(settings, PYTHON)
        assert len(result["hooks"][HOOK_EVENT]) == 2
        assert result["hooks"][HOOK_EVENT][0] == {"matcher": "Bash", "hooks": "not-a-list"}

    @pytest.mark.parametrize("bad_hooks", [None, 5, True, {"nested": "dict"}])
    def test_group_hooks_non_iterable_does_not_crash(self, bad_hooks):
        """Round2 precision follow-up: a string is a weak witness for the
        `isinstance(hooks, list)` guard (it's iterable, so a missing guard
        wouldn't crash — it just wouldn't match). Non-iterable values
        (None/int/bool) are the real witness: without the guard, iterating
        `group.get("hooks")` raises TypeError. Exercised via
        find_mpg_group/has_mpg_hook directly, not just merge_hook."""
        settings = {"hooks": {HOOK_EVENT: [{"matcher": "Bash", "hooks": bad_hooks}]}}
        assert find_mpg_group(settings) is None
        assert has_mpg_hook(settings) is False
        result = merge_hook(settings, PYTHON)
        assert result["hooks"][HOOK_EVENT][0] == {"matcher": "Bash", "hooks": bad_hooks}

    def test_n1_dead_matcher_not_touched_or_fixed(self):
        result = merge_hook(H5_FOREIGN_GROUPS_RICH, PYTHON)
        dead_matcher_group = result["hooks"][HOOK_EVENT][0]
        original_matcher = H5_FOREIGN_GROUPS_RICH["hooks"][HOOK_EVENT][0]["matcher"]
        assert dead_matcher_group["matcher"] == original_matcher

    def test_n2_matcher_omitted_and_wildcard_no_keyerror(self):
        result = merge_hook(N2_MATCHER_OMITTED_AND_WILDCARD, PYTHON)
        assert result["hooks"]["SessionEnd"][0].get("matcher") is None
        assert len(result["hooks"][HOOK_EVENT]) == 2

    def test_n3_foreign_custom_keys_round_trip(self):
        result = merge_hook(H5_FOREIGN_GROUPS_RICH, PYTHON)
        assert result["hooks"]["PreToolUse"][0]["x-omamori-version"] == "0.13.1"

    def test_n4_identity_survives_args_split(self):
        """The identity token is `claude-post-tool-use`, matched as an
        exact `args` element — must match even though the subcommand name
        lives entirely inside `args`, not `command`."""
        settings = merge_hook({}, PYTHON)
        entry = find_mpg_group(settings)["hooks"][0]
        assert "claude-post-tool-use" not in entry["command"]
        assert "claude-post-tool-use" in entry["args"]
        # re-merging must recognize it as mpg's own (in-place refresh, not a dup)
        remerged = merge_hook(settings, PYTHON)
        assert len(find_mpg_group(remerged)["hooks"]) == 1

    def test_n6_many_sibling_keys_survive(self):
        result = merge_hook(H5_FOREIGN_GROUPS_RICH, PYTHON)
        for key in ("effortLevel", "permissions", "statusLine"):
            assert result[key] == H5_FOREIGN_GROUPS_RICH[key]

    def test_foreign_entry_containing_token_as_substring_not_adopted(self):
        """Adversarial: a foreign tool's log path merely *contains* the
        identity token as a substring. Exact-word matching must reject it —
        a false positive here means mpg silently overwrites or deletes an
        unrelated tool's hook group (Codex-proxy 6-B finding)."""
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/usr/bin/logger",
                                "args": [
                                    "--file",
                                    "/var/log/not-claude-post-tool-use-related.log",
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        assert find_mpg_group(settings) is None
        result = merge_hook(settings, PYTHON)
        # foreign group untouched, mpg appended as a second, separate group
        assert result["hooks"][HOOK_EVENT][0] == settings["hooks"][HOOK_EVENT][0]
        assert len(result["hooks"][HOOK_EVENT]) == 2

    def test_foreign_entry_with_dict_valued_arg_not_adopted(self):
        """Adversarial: an `args` element that is a dict (not a plain
        string) containing the token in one of its values. `str()`-coercion
        of the whole list would have matched this before the fix; exact
        membership on `args` elements must not."""
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/usr/bin/some-other-tool",
                                "args": [{"log_tag": "claude-post-tool-use"}],
                            }
                        ],
                    }
                ]
            }
        }
        assert find_mpg_group(settings) is None

    def test_preexisting_duplicate_matching_groups_converge_to_one(self):
        """If a settings file somehow already has 2 groups both matching
        mpg's identity (hand-edit, or a hypothetical earlier-version bug),
        merge_hook must strip all of them and leave exactly 1 — not just
        refresh the first and leave a permanent stale duplicate."""
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/old/py2",
                                "args": ["hook", "claude-post-tool-use"],
                            }
                        ],
                    },
                    {
                        "matcher": "Edit",
                        "hooks": [{"type": "command", "command": "mpg hook claude-post-tool-use"}],
                    },
                ]
            }
        }
        result = merge_hook(settings, PYTHON)
        assert len(result["hooks"][HOOK_EVENT]) == 1
        assert result["hooks"][HOOK_EVENT][0]["hooks"][0]["command"] == PYTHON

    def test_foreign_entry_co_located_in_mpg_group_survives(self):
        """Round1 P1: a group whose `hooks` list mixes an mpg entry with an
        unrelated foreign entry must keep the foreign entry — group-level
        drop/replace (the pre-fix behavior) silently destroyed it."""
        foreign_entry = {"type": "command", "command": "/abs/my-other-tool.sh", "timeout": 5}
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {"type": "command", "command": "mpg hook claude-post-tool-use"},
                            foreign_entry,
                        ],
                    }
                ]
            }
        }
        result = merge_hook(settings, PYTHON)
        all_entries = [e for g in result["hooks"][HOOK_EVENT] for e in g["hooks"]]
        assert foreign_entry in all_entries
        assert find_mpg_group(result) is not None


class TestUnmergeHook:
    def test_foreign_entry_co_located_in_mpg_group_survives_uninstall(self):
        """Round1 P1, uninstall side: the same mixed-group shape must keep
        the foreign entry after mpg's entry is stripped."""
        foreign_entry = {"type": "command", "command": "/abs/my-other-tool.sh", "timeout": 5}
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {"type": "command", "command": "mpg hook claude-post-tool-use"},
                            foreign_entry,
                        ],
                    }
                ]
            }
        }
        result = unmerge_hook(settings)
        all_entries = [e for g in result["hooks"][HOOK_EVENT] for e in g["hooks"]]
        assert foreign_entry in all_entries
        assert find_mpg_group(result) is None

    def test_merge_then_unmerge_of_mixed_group_loses_no_foreign_content(self):
        """End-to-end: merge (migrates the mixed group) then unmerge (removes
        mpg's fresh group) must still preserve the foreign entry throughout,
        even though the exact original group structure isn't recoverable
        (mpg's entry was ambiguously co-mingled with it to begin with)."""
        foreign_entry = {"type": "command", "command": "/abs/my-other-tool.sh", "timeout": 5}
        settings = {
            "hooks": {
                HOOK_EVENT: [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {"type": "command", "command": "mpg hook claude-post-tool-use"},
                            foreign_entry,
                        ],
                    }
                ]
            }
        }
        result = unmerge_hook(merge_hook(settings, PYTHON))
        all_entries = [e for g in result["hooks"][HOOK_EVENT] for e in g["hooks"]]
        assert all_entries == [foreign_entry]
        assert find_mpg_group(result) is None

    @pytest.mark.parametrize(
        "fixture",
        [{}, H3_MODAL_PERMS_ONLY, H4_PRE_TOOL_USE_ONLY, H5_FOREIGN_GROUPS_RICH],
        ids=["h1-empty", "h3-modal-perms", "h4-pre-tool-use", "h5-foreign-groups-rich"],
    )
    def test_symmetric_round_trip(self, fixture):
        """merge then unmerge must restore the exact starting shape, across
        every canonical starting shape (empty / modal / other-event-only /
        rich-foreign-content)."""
        assert unmerge_hook(merge_hook(fixture, PYTHON)) == fixture

    def test_no_op_when_absent(self):
        assert unmerge_hook(H3_MODAL_PERMS_ONLY) == H3_MODAL_PERMS_ONLY

    def test_does_not_mutate_input(self):
        merged = merge_hook(H5_FOREIGN_GROUPS_RICH, PYTHON)
        snapshot = json.loads(json.dumps(merged))
        unmerge_hook(merged)
        assert merged == snapshot

    def test_malformed_hooks_type_is_no_op_not_crash(self):
        settings = {"hooks": "not-an-object"}
        assert unmerge_hook(settings) == settings


class TestIsEphemeralInterpreter:
    @pytest.mark.parametrize(
        "path",
        [
            "/Users/x/.cache/uv/archive-v0/abc/bin/python3",
            "/tmp/uvx-tmp-xyz/bin/python3",
            "/private/var/folders/lm/T/some-tmp/bin/python3",
        ],
    )
    def test_detects_ephemeral_paths(self, path):
        assert is_ephemeral_interpreter(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "/Users/x/claude_workspace/modern-python-guidance/.venv/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/bin/python3",
            # Adversarial (Codex-proxy 6-B finding): "tmp" as a project
            # directory NAME, not the actual OS temp root. A substring
            # search over the whole path would false-positive here.
            "/Users/yotta/tmp/scratch-project/.venv/bin/python3",
            "/home/dev/workspace/tmp/keep-me/.venv/bin/python3",
        ],
    )
    def test_does_not_flag_persistent_paths(self, path):
        assert is_ephemeral_interpreter(path) is False


# --- I/O layer tests: read_settings / write_settings_atomic ---


class TestReadSettings:
    def test_h1_absent_reads_as_empty(self, tmp_path: Path):
        assert read_settings(tmp_path / "settings.local.json") == {}

    def test_reads_valid_json(self, tmp_path: Path):
        p = tmp_path / "settings.local.json"
        p.write_text(json.dumps(H3_MODAL_PERMS_ONLY))
        assert read_settings(p) == H3_MODAL_PERMS_ONLY

    def test_a1_malformed_json_raises(self, tmp_path: Path):
        p = tmp_path / "settings.local.json"
        p.write_text("{not valid")
        with pytest.raises(HookConfigError, match="not valid JSON"):
            read_settings(p)

    def test_a1_top_level_not_object_raises(self, tmp_path: Path):
        p = tmp_path / "settings.local.json"
        p.write_text("[1, 2, 3]")
        with pytest.raises(HookConfigError, match="JSON object"):
            read_settings(p)

    def test_a6_jsonc_comments_rejected_not_silently_tolerated(self, tmp_path: Path):
        p = tmp_path / "settings.local.json"
        p.write_text('{\n  // comment\n  "permissions": {}\n}')
        with pytest.raises(HookConfigError):
            read_settings(p)

    def test_a7_symlink_refused(self, tmp_path: Path):
        real = tmp_path / "real.json"
        real.write_text("{}")
        link = tmp_path / "settings.local.json"
        link.symlink_to(real)
        with pytest.raises(HookConfigError, match="symlink"):
            read_settings(link)

    def test_a7_dangling_symlink_refused(self, tmp_path: Path):
        link = tmp_path / "settings.local.json"
        link.symlink_to(tmp_path / "does-not-exist.json")
        with pytest.raises(HookConfigError, match="symlink"):
            read_settings(link)

    def test_a11_bom_tolerated_via_utf8_sig(self, tmp_path: Path):
        p = tmp_path / "settings.local.json"
        p.write_bytes(b"\xef\xbb\xbf" + json.dumps(H3_MODAL_PERMS_ONLY).encode())
        assert read_settings(p) == H3_MODAL_PERMS_ONLY


class TestWriteSettingsAtomic:
    def test_writes_and_creates_parent_dir(self, tmp_path: Path):
        path = tmp_path / ".claude" / "settings.local.json"
        write_settings_atomic(path, H3_MODAL_PERMS_ONLY)
        assert json.loads(path.read_text()) == H3_MODAL_PERMS_ONLY

    def test_preserves_existing_file_permissions(self, tmp_path: Path):
        """Round1 P2: tempfile.mkstemp creates at 0600 and os.replace keeps
        the new file's mode — without re-applying the original mode, every
        write would silently narrow a pre-existing 0644 file to 0600."""
        path = tmp_path / "settings.local.json"
        path.write_text(json.dumps(H3_MODAL_PERMS_ONLY))
        path.chmod(0o644)
        write_settings_atomic(path, merge_hook(H3_MODAL_PERMS_ONLY, PYTHON))
        assert stat.S_IMODE(path.stat().st_mode) == 0o644

    def test_a1_failure_leaves_original_untouched(self, tmp_path: Path, monkeypatch):
        """Simulate a crash mid-write (os.replace never runs): the original
        file content must survive untouched (atomicity)."""
        path = tmp_path / "settings.local.json"
        path.write_text(json.dumps(H3_MODAL_PERMS_ONLY))

        def _boom(*a, **kw):
            msg = "simulated crash"
            raise OSError(msg)

        monkeypatch.setattr("modern_python_guidance.hook_config.os.replace", _boom)
        with pytest.raises(OSError, match="simulated crash"):
            write_settings_atomic(path, merge_hook(H3_MODAL_PERMS_ONLY, PYTHON))
        assert json.loads(path.read_text()) == H3_MODAL_PERMS_ONLY
        # no leftover temp files
        leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".mpg-settings-")]
        assert leftovers == []

    def test_a10_permission_denied_parent_raises_not_crashes(self, tmp_path: Path):
        """No write permission on the parent chain: mkdir/mkstemp must
        raise a plain OSError (PermissionError) that a caller's `except
        OSError` can catch — not crash with something uncaught, and not
        silently do a partial write."""
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)
        path = locked / ".claude" / "settings.local.json"
        try:
            with pytest.raises(OSError):
                write_settings_atomic(path, H3_MODAL_PERMS_ONLY)
        finally:
            locked.chmod(0o700)  # allow pytest's tmp_path cleanup to remove it

    def test_a7_symlink_target_refused(self, tmp_path: Path):
        real = tmp_path / "real.json"
        real.write_text("{}")
        link = tmp_path / "settings.local.json"
        link.symlink_to(real)
        with pytest.raises(HookConfigError, match="symlink"):
            write_settings_atomic(link, H3_MODAL_PERMS_ONLY)
        # the symlink itself, and its target, must be untouched
        assert link.is_symlink()
        assert real.read_text() == "{}"


class TestSettingsLocalPath:
    def test_resolves_dot_claude_settings_local(self, tmp_path: Path):
        assert settings_local_path(tmp_path) == tmp_path / ".claude" / "settings.local.json"


class TestSymlinkedParentNotes:
    """#170/#192: directories mpg writes through are followed, so say where to.

    The per-file symlink guards in read_settings/write_settings_atomic do not
    cover the directories above the file, and deliberately so — refusing would
    break "config lives elsewhere" setups. What must not happen is following
    them silently. #170 covered `.claude`; #192 covers the directories under it.
    """

    @staticmethod
    def _project(tmp_path: Path) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        return proj

    def _writes(self, proj: Path) -> list[Path]:
        """The three paths mpg writes, as the callers pass them."""
        return [
            proj / ".claude" / "skills" / "modern-python-guidance",
            proj / ".claude" / "rules" / "modern-python.md",
            settings_local_path(proj),
        ]

    def test_empty_for_an_ordinary_tree(self, tmp_path: Path):
        proj = self._project(tmp_path)
        (proj / ".claude" / "skills").mkdir(parents=True)
        (proj / ".claude" / "rules").mkdir(parents=True)
        assert symlinked_parent_notes(proj, self._writes(proj)) == []

    def test_empty_when_absent(self, tmp_path: Path):
        proj = self._project(tmp_path)
        assert symlinked_parent_notes(proj, self._writes(proj)) == []

    @pytest.mark.parametrize("relative", [".claude", ".claude/skills", ".claude/rules"])
    def test_each_write_through_directory_is_reported(self, tmp_path: Path, relative: str):
        """#192: the disclosure must not stop at `.claude`."""
        proj = self._project(tmp_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        link = proj / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(elsewhere, target_is_directory=True)

        notes = symlinked_parent_notes(proj, self._writes(proj))
        assert len(notes) == 1, notes
        assert str(link) in notes[0]
        assert str(elsewhere.resolve()) in notes[0]

    def test_siblings_pointing_elsewhere_are_both_reported(self, tmp_path: Path):
        """Two real destinations must produce two notes.

        The rejected first design reported only the outermost symlink found,
        which would name `skills` and stay silent about `rules` — making
        "mpg discloses where writes land" false in exactly the case where it
        matters most, because the two land in different trees.
        """
        proj = self._project(tmp_path)
        (proj / ".claude").mkdir()
        skills_target = tmp_path / "shared-skills"
        rules_target = tmp_path / "shared-rules"
        skills_target.mkdir()
        rules_target.mkdir()
        (proj / ".claude" / "skills").symlink_to(skills_target, target_is_directory=True)
        (proj / ".claude" / "rules").symlink_to(rules_target, target_is_directory=True)

        notes = symlinked_parent_notes(proj, self._writes(proj))
        assert len(notes) == 2, notes
        joined = "\n".join(notes)
        assert str(skills_target.resolve()) in joined
        assert str(rules_target.resolve()) in joined

    def test_outermost_symlink_collapses_the_inner_ones(self, tmp_path: Path):
        """Once writes leave for the link target, what is inside it is that
        tree's business — reporting it too would imply two destinations."""
        proj = self._project(tmp_path)
        shared = tmp_path / "shared-claude"
        (shared / "skills").mkdir(parents=True)
        (proj / ".claude").symlink_to(shared, target_is_directory=True)
        (tmp_path / "even-further").mkdir()
        # Reached only by following `.claude`, so it must not be named.
        (shared / "skills").rmdir()
        (shared / "skills").symlink_to(tmp_path / "even-further", target_is_directory=True)

        notes = symlinked_parent_notes(proj, self._writes(proj))
        assert len(notes) == 1, notes
        assert str(proj / ".claude") in notes[0]
        assert "even-further" not in notes[0]

    def test_mpg_own_link_is_not_reported(self, tmp_path: Path):
        """The final component is mpg's own artifact. Walking into it would make
        a second `mpg setup` in an ordinary project announce mpg's own links."""
        proj = self._project(tmp_path)
        (proj / ".claude" / "skills").mkdir(parents=True)
        source = tmp_path / "package-skills"
        source.mkdir()
        (proj / ".claude" / "skills" / "modern-python-guidance").symlink_to(
            source, target_is_directory=True
        )

        assert symlinked_parent_notes(proj, self._writes(proj)) == []

    def test_dangling_symlink_still_reports_where_it_points(self, tmp_path: Path):
        proj = self._project(tmp_path)
        (proj / ".claude").symlink_to(tmp_path / "gone", target_is_directory=True)

        notes = symlinked_parent_notes(proj, self._writes(proj))
        assert len(notes) == 1
        assert "gone" in notes[0]

    def test_symlink_loop_degrades_instead_of_raising(self, tmp_path: Path):
        """A loop must neither raise nor produce a note that discloses nothing.

        How `Path.resolve()` reports a loop is version dependent — <= 3.13 raises
        RuntimeError, 3.14 returns the input path unchanged (measured on 3.12.12
        and 3.14.6, and caught by CI when only the first was pinned). Asserting
        on the exception type made this test pass only on the interpreter that
        wrote it; asserting on the *outcome* holds on both.
        """
        proj = self._project(tmp_path)
        (proj / ".claude").symlink_to(proj / "b")
        (proj / "b").symlink_to(proj / ".claude")

        notes = symlinked_parent_notes(proj, self._writes(proj))
        assert len(notes) == 1
        assert "unresolvable" in notes[0]
        # The failure mode this guards: naming `.claude` as its own target.
        assert f"writes to {proj / '.claude'}" not in notes[0]

    def test_paths_outside_the_project_root_are_ignored(self, tmp_path: Path):
        """A caller passing an unrelated absolute path must not crash the run."""
        proj = self._project(tmp_path)
        (proj / ".claude").mkdir()
        assert symlinked_parent_notes(proj, [tmp_path / "somewhere-else" / "x"]) == []

    def test_loop_degrades_for_a_relative_project_root(self, tmp_path: Path, monkeypatch):
        """`--project-dir` is taken as a plain `Path` and may be relative.

        `resolve()` always absolutizes, so comparing its result to a relative
        input never matches — on 3.14, where an unresolvable loop is reported by
        returning the path rather than raising, that made the degradation check
        miss and produced "X is a symlink; mpg writes to <X absolutized>".
        """
        proj = self._project(tmp_path)
        (proj / ".claude").symlink_to(proj / "b")
        (proj / "b").symlink_to(proj / ".claude")
        monkeypatch.chdir(tmp_path)

        relative = Path(proj.name)
        notes = symlinked_parent_notes(relative, [relative / ".claude" / "settings.local.json"])
        assert len(notes) == 1
        assert "unresolvable" in notes[0]
        assert str(proj / ".claude") not in notes[0]


class TestBuildMpgHookEntry:
    def test_uses_command_and_args_not_shell_string(self):
        entry = build_mpg_hook_entry(PYTHON)
        assert entry["command"] == PYTHON
        assert entry["type"] == "command"
        assert isinstance(entry["args"], list)
        assert " " not in entry["command"] or entry["command"] == PYTHON


class TestFindMpgEntries:
    """Entry granularity, matching what `_strip_mpg_entries` removes.

    `merge_hook` promises to converge from any starting state, including one
    that already holds several matching entries. Until now nothing could read
    that state back: the only finder stopped at the first group.
    """

    def _settings(self, *groups: dict) -> dict:
        return {"hooks": {HOOK_EVENT: list(groups)}}

    def _group(self, matcher: str, *commands: str) -> dict:
        return {
            "matcher": matcher,
            "hooks": [build_mpg_hook_entry(command) for command in commands],
        }

    def test_every_entry_is_returned_with_its_group(self):
        settings = self._settings(
            self._group("Edit|Write", "/a/python", "/b/python"),
            self._group("Edit", "/c/python"),
        )
        found = find_mpg_entries(settings)
        assert [entry["command"] for _, entry in found] == ["/a/python", "/b/python", "/c/python"]
        assert [group["matcher"] for group, _ in found] == ["Edit|Write", "Edit|Write", "Edit"]

    def test_foreign_entries_are_not_returned(self):
        group = self._group("Edit|Write", "/a/python")
        group["hooks"].insert(0, {"type": "command", "command": "/somebody/else.sh"})
        found = find_mpg_entries(self._settings(group))
        assert [entry["command"] for _, entry in found] == ["/a/python"]

    def test_the_first_group_finder_is_the_head_of_this_one(self):
        """Two traversals would be two definitions of "an mpg entry"."""
        settings = self._settings(
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "/other.sh"}]},
            self._group("Edit|Write", "/a/python"),
        )
        assert find_mpg_group(settings) is find_mpg_entries(settings)[0][0]
        assert has_mpg_hook(settings)

    def test_shapes_that_hold_nothing_return_empty(self):
        assert find_mpg_entries({}) == []
        assert find_mpg_entries({"hooks": "not a dict"}) == []
        assert find_mpg_entries({"hooks": {HOOK_EVENT: "not a list"}}) == []
        assert find_mpg_entries(self._settings({"hooks": "not a list"})) == []
        assert find_mpg_group({}) is None


class TestMatcherFiresOn:
    """Claude Code decides how to read a matcher from the characters it holds.

    Simple characters make it an exact name or a `|`/`,`-separated list of exact
    names; anything else makes it an unanchored regular expression. Written from
    the hooks reference rather than guessed — the first draft of this change
    treated every matcher as a regex, which quietly turns `Edit|Write` into an
    alternation that also selects `NotebookEdit`.
    """

    def test_the_canonical_matcher_covers_exactly_the_tools_mpg_names(self):
        for tool in HOOK_TOOLS:
            assert matcher_fires_on(HOOK_MATCHER, tool) is True
        assert matcher_fires_on(HOOK_MATCHER, "NotebookEdit") is False
        assert matcher_fires_on(HOOK_MATCHER, "Bash") is False

    def test_the_tool_list_comes_from_the_matcher_mpg_writes(self):
        assert tuple(HOOK_MATCHER.split("|")) == HOOK_TOOLS

    @pytest.mark.parametrize("matcher", [None, "", "*"])
    def test_the_wildcard_forms_select_everything(self, matcher):
        assert matcher_fires_on(matcher, "Edit") is True
        assert matcher_fires_on(matcher, "Bash") is True

    def test_a_comma_list_is_exact_names_too(self):
        assert matcher_fires_on("Edit, Write", "Write") is True
        assert matcher_fires_on("Edit, Write", "Writer") is False

    def test_a_pattern_character_switches_to_an_unanchored_regex(self):
        assert matcher_fires_on("^Edit$", "Edit") is True
        assert matcher_fires_on("Edit.*", "NotebookEdit") is True
        assert matcher_fires_on("^Edit$", "NotebookEdit") is False

    def test_what_cannot_be_evaluated_is_none_rather_than_false(self):
        """`None` is not folded into "does not fire".

        Claude Code runs the regex in JavaScript. A pattern Python refuses is
        one this process has not measured, and reporting it as not firing would
        call a working registration broken.
        """
        assert matcher_fires_on("Edit(", "Edit") is None
        assert matcher_fires_on(42, "Edit") is None

    def test_a_matcher_cannot_end_the_process_it_is_read_by(self):
        """A matcher is untrusted input, and `re` raises more than `re.error`.

        A large enough repetition count comes back as `OverflowError`, which a
        narrow `except re.error` lets through — one line of JSON in a settings
        file, and `mpg doctor` ends in a traceback instead of a report.
        """
        assert matcher_fires_on("(?:a){4294967295}", "Edit") is None

    def test_a_trailing_newline_does_not_pass_for_a_simple_list(self):
        """Python's `$` also matches before a trailing newline.

        `Edit|Write\\n` classified as a simple list reads as covering both
        tools. It holds a character the simple form does not allow, so the real
        rule makes it a regular expression, where `Write` does not match at
        all — the misclassification turns "does not fire" into "fires".
        """
        assert matcher_fires_on("Edit|Write\n", "Edit") is True
        assert matcher_fires_on("Edit|Write\n", "Write") is False


class TestMatchersTheTwoEnginesReadDifferently:
    """#237: Python answering for JavaScript, and the subset where it may.

    Failing to compile was already handled. What was not: a pattern Python
    compiles and JavaScript rejects, which came back as a confident `True` and
    reached the reader as `present` for a hook that never fires.

    The `node_said` column is a measurement (node v26.7.0 against CPython
    3.14.7, 2026-09-04) recorded so a reader can see *why* each row belongs
    here. It is not asserted against: nothing in this process runs node, so
    the column is provenance, and the test itself only checks that a matcher
    the two engines were measured to read differently comes back `None`.
    """

    # (matcher, tool, what node answered). ERROR means SyntaxError there.
    ENGINES_DISAGREE = (
        # Python 3.11's possessive quantifiers. JavaScript has none of them,
        # and this family is the whole reason `+` and `?` are out of the subset.
        ("Edit*+", "Edit", "ERROR"),
        ("Edit++", "Edit", "ERROR"),
        ("Edit?+", "Edit", "ERROR"),
        ("^Edit++$", "Edit", "ERROR"),
        # Named groups are spelled differently; inline flags do not exist there.
        ("(?P<x>Edit)|Write", "Edit", "ERROR"),
        ("(?P<x>Edit)|Write", "Write", "ERROR"),
        ("(?i)edit", "Edit", "ERROR"),
        # Compiles in both, means different things: `\Z` is an anchor in Python
        # and a literal `Z` in JavaScript.
        ("Edit\\Z", "Edit", "false"),
    )

    @pytest.mark.parametrize(
        ("matcher", "tool"),
        [(matcher, tool) for matcher, tool, _node_said in ENGINES_DISAGREE],
        ids=[f"{matcher}-{tool}-node:{said}" for matcher, tool, said in ENGINES_DISAGREE],
    )
    def test_a_matcher_the_engines_read_differently_is_unknown(self, matcher, tool):
        """Every one of these used to return True. Python's answer is not the
        one that matters when node either refuses the pattern or reads it
        another way, so the only honest verdict is "not established".

        What node answered is carried in the test id rather than asserted —
        see the class docstring on why it cannot be a check.
        """
        assert matcher_fires_on(matcher, tool) is None

    def test_the_subset_still_answers_the_matchers_that_agree(self):
        """The control. A guard stuck at `None` passes every assertion above
        and fails here, and so does a subset drawn too narrowly to admit the
        three regex forms the older tests pin."""
        assert matcher_fires_on("Edit|Write", "Edit") is True
        assert matcher_fires_on("Edit|Write", "Bash") is False
        assert matcher_fires_on("^Edit$", "Edit") is True
        assert matcher_fires_on("^Edit$", "NotebookEdit") is False
        assert matcher_fires_on("Edit.*", "NotebookEdit") is True
        assert matcher_fires_on("Edit|Write\n", "Edit") is True

    def test_the_subset_is_the_set_that_was_measured(self):
        """`-` last so it is a literal, `^` not first so it does not negate.

        Getting either wrong silently changes which patterns are admitted:
        a `-` in the middle becomes a range, and a leading `^` inverts the
        whole class — turning the guard into its own opposite while every
        other test in this class still passes.
        """
        admits = hook_config._PORTABLE_MATCHER.fullmatch
        for char in "AZaz09_ ,|.^$*-\n":
            assert admits(char), f"{char!r} should be in the measured subset"
        for char in "()+?[]{}\\/<>%&#@!~`'\"":
            assert not admits(char), f"{char!r} should be outside the measured subset"

    def test_a_tool_name_outside_the_subject_of_the_measurement_is_unknown(self):
        """The equivalence holds for tool names, not for arbitrary strings.

        `$` matches before a trailing newline in Python but not in JavaScript,
        and `.` excludes a different set of line terminators in each. Both are
        reachable only through the tool argument, so the guard lives there —
        as a test, not as a sentence in the docstring.

        Built with `chr()` rather than typed: a review of this change found a
        U+2028 sitting in a source file where a space was intended.
        """
        newline = chr(10)
        assert matcher_fires_on("Edit.*", f"Edit{newline}") is None
        assert matcher_fires_on("Edit.*", f"Edit{chr(0x2028)}") is None
        # The control, twice over: the same regex matcher against a plain name
        # still answers, and the simple form is an exact comparison in both
        # engines, so an odd tool name does not stop it answering either.
        assert matcher_fires_on("Edit.*", "Edit") is True
        assert matcher_fires_on("Edit|Write", f"Edit{newline}") is False
