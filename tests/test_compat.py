from __future__ import annotations

import pytest

from modern_python_guidance.compat import VERSION_RE, token_estimate, version_compatible


class TestVersionCompatible:
    def test_compatible(self):
        assert version_compatible(">=3.9", "3.12") is True

    def test_incompatible(self):
        assert version_compatible(">=3.11", "3.9") is False

    def test_boundary_exact(self):
        assert version_compatible(">=3.11", "3.11") is True

    def test_compound_specifier_pass(self):
        assert version_compatible(">=3.9,<3.13", "3.12") is True

    def test_compound_specifier_fail(self):
        assert version_compatible(">=3.9,<3.13", "3.13") is False

    def test_empty_specifier_matches_all(self):
        assert version_compatible("", "3.12") is True

    def test_invalid_specifier_fail_open(self):
        assert version_compatible("not-valid", "3.12") is True

    def test_invalid_target_fail_open(self):
        assert version_compatible(">=3.9", "abc") is True

    def test_patch_level_target(self):
        assert version_compatible(">=3.9", "3.11.1") is True

    def test_unexpected_error_propagates(self, monkeypatch):
        def _boom(self, *a, **kw):
            raise RuntimeError("unexpected")

        fake = type("Boom", (), {"__init__": _boom, "__contains__": _boom})
        monkeypatch.setattr(
            "modern_python_guidance.compat.SpecifierSet",
            fake,
        )
        with pytest.raises(RuntimeError, match="unexpected"):
            version_compatible(">=3.9", "3.12")


class TestTokenEstimate:
    def test_empty_string(self):
        assert token_estimate("") == 0

    def test_one_char(self):
        assert token_estimate("x") == 0

    def test_three_chars(self):
        assert token_estimate("xxx") == 0

    def test_four_chars(self):
        assert token_estimate("abcd") == 1

    def test_five_chars(self):
        assert token_estimate("xxxxx") == 1

    def test_hundred_chars(self):
        assert token_estimate("x" * 100) == 25


class TestVersionRe:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("3.12", True),
            ("3.12.1", False),
            ("abc", False),
            ("", False),
            ("v3.12", False),
            ("3.", False),
            (".11", False),
            ("03.011", True),
        ],
        ids=[
            "major_minor",
            "patch_no_match",
            "alpha_no_match",
            "empty_no_match",
            "v_prefix_no_match",
            "trailing_dot_no_match",
            "leading_dot_no_match",
            "leading_zeros_match",
        ],
    )
    def test_pattern(self, value: str, expected: bool):
        assert (VERSION_RE.match(value) is not None) is expected
