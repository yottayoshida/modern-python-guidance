"""Weighted keyword search engine for guides."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from modern_python_guidance.compat import token_estimate, version_compatible
from modern_python_guidance.frontmatter import GuideMeta
from modern_python_guidance.guide_index import Guide, GuideIndex

WEIGHT_TAG = 10
WEIGHT_ALIAS = 8
WEIGHT_TITLE = 5
WEIGHT_CATEGORY = 3
WEIGHT_BODY = 2

FREQ_BOOST = {"high": 1.0, "medium": 0.5, "low": 0.0}

MAX_QUERY_LEN = 500
FUZZY_CUTOFF = 0.4
FUZZY_MAX = 3


@dataclass
class SearchResult:
    guide_id: str
    score: float
    meta: GuideMeta
    token_estimate: int
    fuzzy: bool = False
    snippet: str = ""


def search(
    index: GuideIndex,
    query: str,
    *,
    python_version: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    limit = max(1, limit)
    query = query[:MAX_QUERY_LEN].lower()
    tokens = query.split()

    if not tokens:
        return []

    query_idents = frozenset(re.findall(r"[a-zA-Z_]\w+", query))

    results: list[SearchResult] = []

    for guide_id, guide in index.guides.items():
        meta = guide.meta

        if category and meta.category != category:
            continue

        if python_version and not version_compatible(meta.python, python_version):
            continue

        score = _score(meta, tokens, guide.body_tokens, query_idents)

        if score > 0:
            score += FREQ_BOOST.get(meta.frequency, 0.0)
            results.append(
                SearchResult(
                    guide_id=guide_id,
                    score=score,
                    meta=meta,
                    token_estimate=token_estimate(guide.body),
                    snippet=guide.snippet,
                )
            )

    results.sort(key=lambda r: (-r.score, r.guide_id))

    if not results:
        return _fuzzy_fallback(
            index,
            query,
            python_version=python_version,
            category=category,
            limit=limit,
        )

    return results[:limit]


def _score(
    meta: GuideMeta,
    tokens: list[str],
    body_tokens: frozenset[str],
    query_idents: frozenset[str],
) -> float:
    score = 0.0
    tags_lower = [t.lower() for t in meta.tags]
    aliases_lower = [a.lower() for a in meta.aliases]
    title_words = meta.title.lower().split()

    for token in tokens:
        if token in tags_lower:
            score += WEIGHT_TAG
        if token in aliases_lower:
            score += WEIGHT_ALIAS
        if any(token in alias for alias in aliases_lower) and token not in aliases_lower:
            score += WEIGHT_ALIAS * 0.5
        if token in title_words:
            score += WEIGHT_TITLE
        if token == meta.category.lower():
            score += WEIGHT_CATEGORY

    for ident in query_idents:
        if ident in body_tokens:
            score += WEIGHT_BODY

    return score


def _fuzzy_fallback(
    index: GuideIndex,
    query: str,
    *,
    python_version: str | None = None,
    category: str | None = None,
    limit: int = FUZZY_MAX,
) -> list[SearchResult]:
    candidates: dict[str, Guide] = {}
    for guide_id, guide in index.guides.items():
        if category and guide.meta.category != category:
            continue
        if python_version and not version_compatible(guide.meta.python, python_version):
            continue
        candidates[guide_id] = guide

    if not candidates:
        return []

    match_pool: list[str] = []
    pool_to_guides: dict[str, list[str]] = {}

    for guide_id, guide in candidates.items():
        for term in [guide_id, guide.meta.title.lower()] + [t.lower() for t in guide.meta.tags]:
            if term not in pool_to_guides:
                match_pool.append(term)
                pool_to_guides[term] = []
            pool_to_guides[term].append(guide_id)

    matches = difflib.get_close_matches(query, match_pool, n=FUZZY_MAX * 2, cutoff=FUZZY_CUTOFF)

    seen: set[str] = set()
    results: list[SearchResult] = []
    for match in matches:
        ratio = difflib.SequenceMatcher(None, query, match).ratio()
        for guide_id in pool_to_guides[match]:
            if guide_id in seen:
                continue
            seen.add(guide_id)
            guide = candidates[guide_id]
            results.append(
                SearchResult(
                    guide_id=guide_id,
                    score=round(ratio, 3),
                    meta=guide.meta,
                    token_estimate=token_estimate(guide.body),
                    fuzzy=True,
                    snippet=guide.snippet,
                )
            )

    results.sort(key=lambda r: (-r.score, r.guide_id))
    return results[: min(limit, FUZZY_MAX)]
