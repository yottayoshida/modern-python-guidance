"""Sync tests: verify SKILL.md stays consistent with guide files and README.

Verification IDs from /plan QA shift-left:
  V-001  SKILL.md guide IDs reference existing guide files
  V-002  SKILL.md token count <= 1300 (chars/4)
  V-009  All embedded guide IDs have frequency: high
  V-010  README Quick start guide IDs reference existing guide files
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modern_python_guidance.guide_index import build_index

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "skills" / "modern-python-guidance" / "SKILL.md"
README_MD = REPO_ROOT / "README.md"
GUIDES_DIR = REPO_ROOT / "skills" / "modern-python-guidance" / "guides"

EMBEDDED_GUIDE_IDS = [
    "pydantic-v2-validators",
    "pydantic-v2-config",
    "pydantic-v2-model-api",
    "fastapi-lifespan",
    "fastapi-annotated-depends",
    "httpx-async-client-reuse",
    "taskgroup-over-gather",
    "pyproject-toml-over-setup",
    "safe-subprocess",
    "sqlalchemy-2-style",
    "sqlalchemy-mapped-column",
]


@pytest.fixture(scope="module")
def guide_index():
    return build_index(GUIDES_DIR)


@pytest.fixture(scope="module")
def skill_text():
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme_text():
    return README_MD.read_text(encoding="utf-8")


def _extract_backtick_ids(text: str) -> list[str]:
    """Extract guide IDs from backtick-quoted strings in the catalog section."""
    return re.findall(r"`([a-z][a-z0-9-]+)`", text)


class TestV001SkillGuideSync:
    """V-001: SKILL.md guide IDs reference existing guide files."""

    def test_embedded_guides_exist(self, guide_index):
        for guide_id in EMBEDDED_GUIDE_IDS:
            assert guide_index.get(guide_id) is not None, (
                f"Embedded guide '{guide_id}' not found in guides/"
            )

    def test_catalog_heading_exists(self, skill_text):
        assert "## All 41 guides by category" in skill_text, (
            "Catalog heading missing from SKILL.md"
        )

    def test_catalog_ids_exist(self, skill_text, guide_index):
        catalog_section = skill_text.split("## All 41 guides by category")[-1]
        ids_in_catalog = _extract_backtick_ids(catalog_section)
        for guide_id in ids_in_catalog:
            assert guide_index.get(guide_id) is not None, (
                f"Catalog guide '{guide_id}' not found in guides/"
            )

    def test_catalog_count_matches(self, guide_index, skill_text):
        assert "41 guides" in skill_text
        assert len(guide_index) == 41, (
            f"SKILL.md says 41 guides but found {len(guide_index)}"
        )

    def test_catalog_covers_all_guides(self, skill_text, guide_index):
        """Reverse check: every guide ID appears in the catalog section."""
        catalog_section = skill_text.split("## All 41 guides by category")[-1]
        catalog_ids = set(_extract_backtick_ids(catalog_section))
        for guide_id in guide_index.guides:
            assert guide_id in catalog_ids, (
                f"Guide '{guide_id}' exists in guides/ but missing from catalog"
            )


class TestV002TokenBudget:
    """V-002: SKILL.md token count <= 1300 (chars/4)."""

    def test_token_budget(self, skill_text):
        tokens = len(skill_text) // 4
        assert tokens <= 1300, (
            f"SKILL.md is {tokens} tokens (chars/4), budget is 1300"
        )


class TestV009EmbeddedFrequency:
    """V-009: All embedded guide IDs have frequency: high."""

    def test_all_high_frequency(self, guide_index):
        for guide_id in EMBEDDED_GUIDE_IDS:
            guide = guide_index.get(guide_id)
            assert guide is not None, f"Guide '{guide_id}' not found"
            assert guide.meta.frequency == "high", (
                f"Embedded guide '{guide_id}' has frequency "
                f"'{guide.meta.frequency}', expected 'high'"
            )


class TestV010ReadmeGuideIds:
    """V-010: README Quick start guide IDs reference existing guide files."""

    def test_readme_guide_ids_exist(self, readme_text, guide_index):
        ids_in_readme = re.findall(r"mpg retrieve\s+([a-z][a-z0-9-]+)", readme_text)
        for guide_id in ids_in_readme:
            assert guide_index.get(guide_id) is not None, (
                f"README references guide '{guide_id}' which doesn't exist"
            )
