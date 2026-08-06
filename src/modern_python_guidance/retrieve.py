"""Guide retrieval and JSON rendering."""

from __future__ import annotations

import difflib
import json
from typing import Any

from modern_python_guidance import __version__
from modern_python_guidance.compat import token_estimate, version_compatible
from modern_python_guidance.dependency_compat import (
    DependencyAssessment,
    DependencyContext,
    assess_dependencies,
)
from modern_python_guidance.guide_index import Guide, GuideIndex
from modern_python_guidance.version_detect import resolve_python_version

MAX_ID_LEN = 200
_SUGGEST_CUTOFF = 0.5
_SUGGEST_MAX = 3


def suggest_ids(index: GuideIndex, missing_id: str) -> list[str]:
    if not isinstance(missing_id, str):
        return []
    truncated = missing_id[:MAX_ID_LEN].lower()
    all_ids = list(index.guides.keys())
    return difflib.get_close_matches(truncated, all_ids, n=_SUGGEST_MAX, cutoff=_SUGGEST_CUTOFF)


def retrieve(
    index: GuideIndex,
    guide_ids: list[str],
    *,
    python_version: str | None = None,
    dependency_context: DependencyContext | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for guide_id in guide_ids:
        guide = index.get(guide_id)
        if guide is None:
            continue
        results.append(
            _render(
                guide,
                python_version=python_version,
                dependency_context=dependency_context,
            )
        )

    return results


def retrieve_json(
    index: GuideIndex,
    guide_ids: list[str],
    *,
    python_version: str | None = None,
    dependency_context: DependencyContext | None = None,
) -> str:
    results = retrieve(
        index,
        guide_ids,
        python_version=python_version,
        dependency_context=dependency_context,
    )
    resolution = resolve_python_version(explicit_version=python_version)
    for result in results:
        result["target_python"] = resolution.as_dict()
    return json.dumps(results, indent=2, ensure_ascii=False)


def _render(
    guide: Guide,
    *,
    python_version: str | None = None,
    dependency_context: DependencyContext | None = None,
) -> dict[str, Any]:
    ver_match = True
    if python_version:
        ver_match = version_compatible(guide.meta.python, python_version)
    assessment = _assess_guide(guide, dependency_context)

    return {
        "id": guide.meta.id,
        "title": guide.meta.title,
        "category": guide.meta.category,
        "layer": guide.meta.layer,
        "python": guide.meta.python,
        "frequency": guide.meta.frequency,
        "version_match": ver_match,
        "content": guide.body,
        "token_estimate": token_estimate(guide.body),
        "source": f"modern-python-guidance v{__version__}",
        "dependency_requirements": {
            "packages": list(guide.meta.applies_to_packages),
            "tools": list(guide.meta.applies_to_tools),
        },
        "dependency_compatibility": {
            "status": assessment.status,
            "evidence": [
                {
                    "kind": fact.kind,
                    "name": fact.name,
                    "version": fact.version,
                    "specifier": fact.specifier,
                    "source": fact.source,
                }
                for fact in assessment.evidence
            ],
            "reasons": list(assessment.reasons),
        },
    }


def _assess_guide(
    guide: Guide, dependency_context: DependencyContext | None
) -> DependencyAssessment:
    requirements = tuple(guide.meta.applies_to_packages) + tuple(guide.meta.applies_to_tools)
    if dependency_context is None:
        return DependencyAssessment("confirmed", requirements, (), ())
    return assess_dependencies(
        package_requirements=guide.meta.applies_to_packages,
        tool_requirements=guide.meta.applies_to_tools,
        context=dependency_context,
    )
