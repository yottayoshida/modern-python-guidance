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

from modern_python_guidance.hook_config import (
    HOOK_EVENT,
    HookConfigError,
    build_mpg_hook_entry,
    find_mpg_group,
    has_mpg_hook,
    is_ephemeral_interpreter,
    merge_hook,
    read_settings,
    settings_local_path,
    symlinked_claude_note,
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


class TestSymlinkedClaudeNote:
    """#170: a symlinked `.claude` directory is followed, so say where writes go.

    The per-file symlink guards in read_settings/write_settings_atomic do not
    cover the parent directory, and deliberately so — refusing would break
    "config lives elsewhere" setups. What must not happen is following it
    silently.
    """

    def test_none_for_an_ordinary_directory(self, tmp_path: Path):
        (tmp_path / ".claude").mkdir()
        assert symlinked_claude_note(tmp_path) is None

    def test_none_when_absent(self, tmp_path: Path):
        assert symlinked_claude_note(tmp_path) is None

    def test_names_the_resolved_target(self, tmp_path: Path):
        elsewhere = tmp_path / "shared-claude"
        elsewhere.mkdir()
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".claude").symlink_to(elsewhere, target_is_directory=True)

        note = symlinked_claude_note(proj)
        assert note is not None
        assert str(elsewhere.resolve()) in note
        assert "symlink" in note

    def test_dangling_symlink_still_reports_where_it_points(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".claude").symlink_to(tmp_path / "gone", target_is_directory=True)

        note = symlinked_claude_note(proj)
        assert note is not None
        assert "gone" in note

    def test_symlink_loop_degrades_instead_of_raising(self, tmp_path: Path):
        """`Path.resolve()` raises RuntimeError on a loop. A note that cannot
        name its target must not take down an otherwise-fine setup run."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".claude").symlink_to(proj / "b")
        (proj / "b").symlink_to(proj / ".claude")

        note = symlinked_claude_note(proj)
        assert note is not None
        assert "unresolvable" in note
        assert "RuntimeError" in note


class TestBuildMpgHookEntry:
    def test_uses_command_and_args_not_shell_string(self):
        entry = build_mpg_hook_entry(PYTHON)
        assert entry["command"] == PYTHON
        assert entry["type"] == "command"
        assert isinstance(entry["args"], list)
        assert " " not in entry["command"] or entry["command"] == PYTHON
