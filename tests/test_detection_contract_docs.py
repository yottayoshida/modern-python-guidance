from __future__ import annotations

from pathlib import Path

from modern_python_guidance.detection_coverage import detection_coverage
from modern_python_guidance.guide_index import build_index

README = Path(__file__).parents[1] / "README.md"
START = "<!-- mpg-check-coverage:start -->"
END = "<!-- mpg-check-coverage:end -->"


def _block(text: str) -> str:
    start = text.index(START)
    end = text.index(END, start) + len(END)
    return text[start:end]


def _expected_block() -> str:
    coverage = detection_coverage(build_index(), python_version=None, dependency_context=None)
    advisory_ids = ", ".join(f"`{guide_id}`" for guide_id in coverage.advisory_only_ids)
    return "\n".join(
        [
            START,
            (
                f"`mpg check` and the PostToolUse hook automatically check only guides with a "
                f"detector for the target Python/dependency context. The current catalog has "
                f"{coverage.detectable_count} detectable guides out of {coverage.catalog_guides}; "
                f"{coverage.advisory_only_count} are advisory-only and are not claimed as "
                "actively checked."
            ),
            f"Advisory-only guides: {advisory_ids}.",
            (
                "A clean automatic check does not certify advisory-only guidance. Use "
                "`mpg list --format json` or MCP metadata to inspect each guide's detection "
                "status."
            ),
            END,
        ]
    )


def test_readme_coverage_block_matches_real_catalog() -> None:
    text = README.read_text(encoding="utf-8")

    assert _block(text) == _expected_block()


def test_readme_does_not_claim_catalog_availability_is_active_checking() -> None:
    text = README.read_text(encoding="utf-8")

    assert "full 41-guide catalog" not in text
    assert "all 41 guides" not in text
    assert "#152" in text


def test_readme_delivery_claim_matches_the_rule_paths() -> None:
    """README says the Rules file loads on Python files *and* project config.
    That is a claim about `RULE_FRONTMATTER`, not about prose.

    A plan for #208 asserted the opposite — that Rules covered `.py` only —
    and built a delivery model on top of it, concluding that the toolchain
    guides were out of reach. Nothing here would have caught it: the paths
    list had never been read back by anything that also read the README.
    """
    from modern_python_guidance.setup_cmd import RULE_FRONTMATTER

    text = README.read_text(encoding="utf-8")
    for config_path in ("pyproject.toml", "requirements*.txt", "setup.cfg"):
        assert config_path in RULE_FRONTMATTER, (
            f"{config_path} left the rule paths — the README claim is now false"
        )
        assert config_path in text, (
            f"README no longer names {config_path}, which the rule paths still cover"
        )
