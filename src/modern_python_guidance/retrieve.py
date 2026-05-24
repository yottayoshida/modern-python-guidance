"""Guide retrieval and JSON rendering."""

from __future__ import annotations

import json
from typing import Any

from modern_python_guidance import __version__
from modern_python_guidance.compat import token_estimate, version_compatible
from modern_python_guidance.guide_index import Guide, GuideIndex


def retrieve(
    index: GuideIndex,
    guide_ids: list[str],
    *,
    python_version: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for guide_id in guide_ids:
        guide = index.get(guide_id)
        if guide is None:
            continue
        results.append(_render(guide, python_version=python_version))

    return results


def retrieve_json(
    index: GuideIndex,
    guide_ids: list[str],
    *,
    python_version: str | None = None,
) -> str:
    results = retrieve(index, guide_ids, python_version=python_version)
    return json.dumps(results, indent=2, ensure_ascii=False)


def _render(guide: Guide, *, python_version: str | None = None) -> dict[str, Any]:
    ver_match = True
    if python_version:
        ver_match = version_compatible(guide.meta.python, python_version)

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
    }
