from __future__ import annotations

from pathlib import Path

from modern_python_guidance.check import check_file
from modern_python_guidance.dependency_compat import DependencyContext, DependencyFact
from modern_python_guidance.detection_coverage import (
    detection_coverage,
    detection_metadata,
    guide_detection,
)
from modern_python_guidance.frontmatter import GuideMeta
from modern_python_guidance.guide_index import Guide, GuideIndex, build_index


def _meta(
    guide_id: str,
    *,
    python: str = ">=3.9",
    detect_patterns: list[str] | None = None,
    detect_names: list[str] | None = None,
    applies_to_packages: list[str] | None = None,
) -> GuideMeta:
    return GuideMeta(
        id=guide_id,
        title=guide_id,
        category="test",
        layer=1,
        tags=["test"],
        python=python,
        frequency="high",
        detect_patterns=detect_patterns,
        detect_names=detect_names,
        applies_to_packages=applies_to_packages or [],
    )


def _guide(meta: GuideMeta, body: str = "") -> Guide:
    return Guide(meta=meta, body=body, source_path=f"{meta.id}.md")


def _index(*guides: Guide) -> GuideIndex:
    return GuideIndex({guide.meta.id: guide for guide in guides})


def _context(*facts: DependencyFact) -> DependencyContext:
    return DependencyContext({(fact.kind, fact.name): (fact,) for fact in facts})


def test_guide_detection_reports_each_effective_method() -> None:
    regex = _guide(_meta("regex", detect_patterns=[r"legacy_call"]))
    ast_name = _guide(_meta("ast-name", detect_patterns=[], detect_names=["pkg.legacy_call"]))
    both = _guide(
        _meta("both", detect_patterns=[r"legacy_call"], detect_names=["pkg.legacy_call"])
    )
    advisory = _guide(_meta("advisory", detect_patterns=[], detect_names=[]))

    assert guide_detection(regex).status == "detectable"
    assert guide_detection(regex).methods == ("regex",)
    assert guide_detection(ast_name).methods == ("ast-name",)
    assert guide_detection(both).methods == ("regex", "ast-name")
    assert guide_detection(advisory).status == "advisory-only"
    assert guide_detection(advisory).methods == ()


def test_guide_detection_counts_bad_block_fallback_as_regex() -> None:
    guide = _guide(
        _meta("fallback", detect_patterns=None),
        "## BAD\n```python\nfrom old_package import thing\n```\n",
    )

    assert guide_detection(guide).status == "detectable"
    assert guide_detection(guide).methods == ("regex",)


def test_bad_block_fallback_parity_with_check_file(tmp_path: Path) -> None:
    guide = _guide(
        _meta("fallback", detect_patterns=None),
        "## BAD\n```python\nfrom old_package import thing\n```\n",
    )
    path = tmp_path / "bad.py"
    path.write_text("from old_package import thing\n", encoding="utf-8")

    matches = check_file(path, _index(guide))
    coverage = detection_coverage(_index(guide), python_version=None, dependency_context=None)

    assert {match.guide_id for match in matches} == {"fallback"}
    assert coverage.detectable_ids == ("fallback",)


def test_overlapping_guides_are_both_capable_even_when_same_line_is_deduplicated(
    tmp_path: Path,
) -> None:
    first = _guide(_meta("first", detect_patterns=[r"legacy_call"]))
    second = _guide(_meta("second", detect_patterns=[r"legacy_call"]))
    index = _index(first, second)
    path = tmp_path / "bad.py"
    path.write_text("legacy_call()\n", encoding="utf-8")

    matches = check_file(path, index)
    coverage = detection_coverage(index, python_version=None, dependency_context=None)

    assert len(matches) == 1
    assert coverage.detectable_ids == ("first", "second")


def test_detection_coverage_json_shape_is_target_specific() -> None:
    index = _index(
        _guide(_meta("detectable", detect_patterns=[r"legacy"])),
        _guide(_meta("advisory", detect_patterns=[], detect_names=[])),
    )

    coverage = detection_coverage(index, python_version=None, dependency_context=None)

    assert coverage.as_dict() == {
        "catalog_guides": 2,
        "applicable_guides": 2,
        "detectable_guides": 1,
        "advisory_only_guides": 1,
        "advisory_only_ids": ["advisory"],
    }


def test_detection_coverage_filters_version_and_incompatible_dependency() -> None:
    index = _index(
        _guide(_meta("detectable", detect_patterns=[r"legacy"])),
        _guide(_meta("advisory", detect_patterns=[], detect_names=[])),
        _guide(_meta("too-new", python=">=3.12", detect_patterns=[r"legacy"])),
        _guide(
            _meta(
                "incompatible",
                detect_patterns=[r"legacy"],
                applies_to_packages=["pydantic>=2"],
            )
        ),
        _guide(
            _meta(
                "unknown-is-applicable",
                detect_patterns=[],
                detect_names=[],
                applies_to_packages=["fastapi>=2"],
            )
        ),
    )
    context = _context(
        DependencyFact("package", "pydantic", "1.10.15", None, "project.dependencies")
    )

    coverage = detection_coverage(index, python_version="3.11", dependency_context=context)

    assert coverage.catalog_guides == 5
    assert coverage.applicable_guides == 3
    assert coverage.detectable_ids == ("detectable",)
    assert coverage.advisory_only_ids == ("advisory", "unknown-is-applicable")


def test_real_catalog_has_expected_detection_buckets() -> None:
    coverage = detection_coverage(build_index(), python_version=None, dependency_context=None)

    assert coverage.catalog_guides == 41
    assert len(coverage.detectable_ids) == 26
    assert len(coverage.advisory_only_ids) == 15
    assert set(coverage.detectable_ids).isdisjoint(coverage.advisory_only_ids)


def test_detection_metadata_is_json_ready_and_stable() -> None:
    guide = _guide(
        _meta("both", detect_patterns=[r"legacy"], detect_names=["pkg.legacy"])
    )

    assert detection_metadata(guide) == {
        "detection": {"status": "detectable", "methods": ["regex", "ast-name"]}
    }
