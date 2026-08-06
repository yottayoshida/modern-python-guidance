"""Derive the guide detection capability and target-specific check scope.

This module is the single source for what the scanner can actually consume.
The check engine and user-facing metadata both use these helpers so a guide
cannot be reported as detectable while its effective patterns are ignored.
The coverage IDs describe guide-level detector capability, not a promise that
every guide will be surfaced for every file: same-line matches are intentionally
deduplicated by the presentation layer in ``check_file``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from modern_python_guidance.compat import version_compatible
from modern_python_guidance.dependency_compat import (
    DependencyAssessment,
    DependencyContext,
    assess_dependencies,
)
from modern_python_guidance.frontmatter import GuideMeta
from modern_python_guidance.guide_index import Guide, GuideIndex, _code_lines

DetectionStatus = Literal["detectable", "advisory-only"]
DetectionMethod = Literal["regex", "ast-name"]


@dataclass(frozen=True)
class GuideDetection:
    status: DetectionStatus
    methods: tuple[DetectionMethod, ...]


@dataclass(frozen=True)
class DetectionCoverage:
    catalog_guides: int
    applicable_guides: int
    detectable_ids: tuple[str, ...]
    advisory_only_ids: tuple[str, ...]

    @property
    def advisory_only_count(self) -> int:
        return len(self.advisory_only_ids)

    @property
    def detectable_count(self) -> int:
        return len(self.detectable_ids)

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON shape used by CLI check output."""
        return {
            "catalog_guides": self.catalog_guides,
            "applicable_guides": self.applicable_guides,
            "detectable_guides": self.detectable_count,
            "advisory_only_guides": self.advisory_only_count,
            "advisory_only_ids": list(self.advisory_only_ids),
        }


def effective_regex_patterns(guide: Guide) -> tuple[str, ...]:
    """Return valid regex sources consumed by the check engine for ``guide``."""
    if guide.meta.detect_patterns is not None:
        raw_patterns = guide.meta.detect_patterns
    else:
        raw_patterns = _auto_extract_patterns(guide)

    valid_patterns: list[str] = []
    for pattern in raw_patterns:
        try:
            re.compile(pattern)
        except re.error:
            continue
        valid_patterns.append(pattern)
    return tuple(valid_patterns)


def guide_detection(guide: Guide) -> GuideDetection:
    """Return the detection methods that can produce a finding for ``guide``."""
    methods: list[DetectionMethod] = []
    if effective_regex_patterns(guide):
        methods.append("regex")
    if guide.meta.detect_names:
        methods.append("ast-name")
    return GuideDetection(
        status="detectable" if methods else "advisory-only",
        methods=tuple(methods),
    )


def detection_metadata(guide: Guide) -> dict[str, object]:
    """Return the stable additive JSON shape for one guide's capability."""
    detection = guide_detection(guide)
    return {
        "detection": {
            "status": detection.status,
            "methods": list(detection.methods),
        }
    }


def detection_coverage(
    index: GuideIndex,
    *,
    python_version: str | None,
    dependency_context: DependencyContext | None,
) -> DetectionCoverage:
    """Summarize detection capability for guides applicable to a target.

    Version-incompatible and proven dependency-incompatible guides are omitted
    from the applicable denominator. Unknown dependency evidence remains in
    scope and is therefore visible as a possible advisory-only gap.
    """
    detectable_ids: list[str] = []
    advisory_only_ids: list[str] = []
    applicable_guides = 0

    for guide in index.guides.values():
        if python_version and not version_compatible(guide.meta.python, python_version):
            continue
        if _assess_guide(guide.meta, dependency_context).status == "incompatible":
            continue

        applicable_guides += 1
        detection = guide_detection(guide)
        target_ids = detectable_ids if detection.status == "detectable" else advisory_only_ids
        target_ids.append(guide.meta.id)

    return DetectionCoverage(
        catalog_guides=len(index),
        applicable_guides=applicable_guides,
        detectable_ids=tuple(sorted(detectable_ids)),
        advisory_only_ids=tuple(sorted(advisory_only_ids)),
    )


def _auto_extract_patterns(guide: Guide) -> list[str]:
    bad_lines = _code_lines(guide.body, "## BAD")
    patterns: list[str] = []
    for line in bad_lines:
        stripped = line.strip()
        if stripped.startswith(("from ", "import ")):
            patterns.append(re.escape(stripped))
        elif stripped.startswith("@"):
            parts = stripped.split("(", 1)
            patterns.append(re.escape(parts[0]))
    return patterns


def _assess_guide(
    meta: GuideMeta, dependency_context: DependencyContext | None
) -> DependencyAssessment:
    requirements = tuple(meta.applies_to_packages) + tuple(meta.applies_to_tools)
    if dependency_context is None:
        return DependencyAssessment("confirmed", requirements, (), ())
    return assess_dependencies(
        package_requirements=meta.applies_to_packages,
        tool_requirements=meta.applies_to_tools,
        context=dependency_context,
    )
