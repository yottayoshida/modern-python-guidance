"""Conservative, dependency-aware guide applicability assessment.

The assessor deliberately proves compatibility only from unambiguous project
evidence.  It never imports the target project or treats the interpreter that
runs mpg as evidence about that project.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

DependencyKind = Literal["package", "tool"]
DependencyStatus = Literal["confirmed", "incompatible", "unknown"]


@dataclass(frozen=True)
class DependencyFact:
    """A single read-only observation about a package or development tool."""

    kind: DependencyKind
    name: str
    version: str | None
    specifier: str | None
    source: str

    def __post_init__(self) -> None:
        if self.kind not in ("package", "tool"):
            raise ValueError(f"Unsupported dependency kind: {self.kind!r}")
        object.__setattr__(self, "name", canonicalize_name(self.name))


@dataclass(frozen=True)
class DependencyContext:
    """Collected project evidence, keyed by normalized ``(kind, name)``."""

    facts: Mapping[tuple[DependencyKind, str], tuple[DependencyFact, ...]]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized: dict[tuple[DependencyKind, str], tuple[DependencyFact, ...]] = {}
        for (kind, name), facts in self.facts.items():
            if kind not in ("package", "tool"):
                raise ValueError(f"Unsupported dependency kind: {kind!r}")
            key = (kind, canonicalize_name(name))
            normalized[key] = tuple(facts)
        object.__setattr__(self, "facts", MappingProxyType(normalized))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class DependencyAssessment:
    """The applicability result, supporting observations, and rationale."""

    status: DependencyStatus
    requirements: tuple[str, ...]
    evidence: tuple[DependencyFact, ...]
    reasons: tuple[str, ...]


def assess_dependencies(
    *,
    package_requirements: tuple[str, ...] | list[str],
    tool_requirements: tuple[str, ...] | list[str],
    context: DependencyContext,
) -> DependencyAssessment:
    """Assess requirements as confirmed, incompatible, or safely unknown.

    A guide with several requirements is confirmed only when every requirement
    is confirmed.  Any proven mismatch makes it incompatible; all remaining
    uncertainty is kept as ``unknown`` rather than guessed.
    """
    requirements = tuple(package_requirements) + tuple(tool_requirements)
    evaluations: list[tuple[DependencyStatus, tuple[DependencyFact, ...], str]] = []
    for kind, declared in (("package", package_requirements), ("tool", tool_requirements)):
        for requirement_text in declared:
            evaluations.append(_assess_requirement(kind, requirement_text, context))

    evidence = tuple(fact for _, facts, _ in evaluations for fact in facts)
    reasons = tuple(reason for _, _, reason in evaluations)
    if any(status == "incompatible" for status, _, _ in evaluations):
        status: DependencyStatus = "incompatible"
    elif all(status == "confirmed" for status, _, _ in evaluations):
        status = "confirmed"
    else:
        status = "unknown"
    return DependencyAssessment(status, requirements, evidence, reasons)


def _assess_requirement(
    kind: DependencyKind, requirement_text: str, context: DependencyContext
) -> tuple[DependencyStatus, tuple[DependencyFact, ...], str]:
    try:
        requirement = Requirement(requirement_text)
    except InvalidRequirement:
        return "unknown", (), f"Invalid guide requirement: {requirement_text!r}"

    key = (kind, canonicalize_name(requirement.name))
    facts = context.facts.get(key, ())
    if not facts:
        return "unknown", (), f"No project evidence for {kind} {requirement.name}"

    selected, priority = _select_evidence(facts)
    if not selected:
        return (
            "unknown",
            facts,
            f"Only non-confirming evidence exists for {kind} {requirement.name}",
        )
    if _conflicts(selected):
        return (
            "unknown",
            selected,
            f"Conflicting {priority} evidence for {kind} {requirement.name}",
        )
    if priority == "lock":
        declaration_status = _check_lock_declarations(facts)
        if declaration_status != "consistent":
            return (
                "unknown",
                selected,
                (
                    "Lock evidence conflicts with or cannot validate active declaration "
                    f"for {requirement.name}"
                ),
            )

    fact = selected[0]
    if fact.version is not None:
        try:
            compatible = Version(fact.version) in requirement.specifier
        except (InvalidVersion, InvalidSpecifier):
            return (
                "unknown",
                selected,
                f"Unsupported exact version evidence for {requirement.name}",
            )
        return (
            ("confirmed" if compatible else "incompatible"),
            selected,
            (
                f"Exact {priority} version {fact.version} "
                f"{'matches' if compatible else 'does not match'} {requirement}"
            ),
        )

    # A bare guide requirement only asks whether the dependency is declared;
    # a concrete project declaration proves that without needing a version.
    if not str(requirement.specifier):
        return (
            "confirmed",
            selected,
            f"Declared {priority} evidence exists for {requirement.name}",
        )
    if not fact.specifier:
        return (
            "unknown",
            selected,
            f"{priority.capitalize()} evidence for {requirement.name} is unpinned",
        )

    relation = _range_relation(fact.specifier, str(requirement.specifier))
    if relation == "subset":
        return (
            "confirmed",
            selected,
            f"Declared range {fact.specifier} is within {requirement.specifier}",
        )
    if relation == "disjoint":
        return (
            "incompatible",
            selected,
            f"Declared range {fact.specifier} is disjoint from {requirement.specifier}",
        )
    return (
        "unknown",
        selected,
        f"Declared range {fact.specifier} overlaps or cannot prove {requirement.specifier}",
    )


def _check_lock_declarations(
    facts: tuple[DependencyFact, ...],
) -> Literal["consistent", "conflicting", "unsupported"]:
    declarations = tuple(fact for fact in facts if _source_priority(fact.source) == 2)
    if not declarations:
        return "consistent"
    if _conflicts(declarations):
        return "conflicting"
    lock_versions = tuple(
        fact.version for fact in facts if _source_priority(fact.source) == 3 and fact.version
    )
    if len(set(lock_versions)) != 1:
        return "conflicting"
    for declaration in declarations:
        if not declaration.specifier:
            continue
        try:
            if _to_interval(declaration.specifier) is None:
                return "unsupported"
            version = Version(lock_versions[0])
            compatible = version in SpecifierSet(declaration.specifier)
        except (InvalidVersion, InvalidSpecifier, StopIteration):
            return "unsupported"
        if not compatible:
            return "conflicting"
    return "consistent"


def _select_evidence(facts: tuple[DependencyFact, ...]) -> tuple[tuple[DependencyFact, ...], str]:
    ranked = [(fact, _source_priority(fact.source)) for fact in facts]
    useful = [(fact, priority) for fact, priority in ranked if priority > 0]
    if not useful:
        return (), "non-confirming"
    highest = max(priority for _, priority in useful)
    selected = tuple(fact for fact, priority in useful if priority == highest)
    labels = {4: "override", 3: "lock", 2: "declared"}
    return selected, labels[highest]


def _source_priority(source: str) -> int:
    if source == "override":
        return 4
    if source in {"uv.lock", "poetry.lock"}:
        return 3
    if source in {"project.dependencies", "poetry.dependencies", "build-system.requires"}:
        return 2
    # Optional and group dependencies may not be active, and tool config only
    # establishes configuration, not the tool installed in the target env.
    return 0


def _conflicts(facts: tuple[DependencyFact, ...]) -> bool:
    identities = {(fact.version, fact.specifier) for fact in facts}
    return len(identities) > 1


@dataclass(frozen=True)
class _Interval:
    lower: Version | None = None
    lower_inclusive: bool = True
    upper: Version | None = None
    upper_inclusive: bool = True


def _range_relation(candidate: str, guide: str) -> Literal["subset", "disjoint", "overlap"]:
    candidate_interval = _to_interval(candidate)
    guide_interval = _to_interval(guide)
    if candidate_interval is None or guide_interval is None:
        return "overlap"
    if _disjoint(candidate_interval, guide_interval):
        return "disjoint"
    if _is_subset(candidate_interval, guide_interval):
        return "subset"
    return "overlap"


def _to_interval(specifier_text: str) -> _Interval | None:
    try:
        specifiers = list(SpecifierSet(specifier_text))
    except InvalidSpecifier:
        return None
    if not specifiers:
        return None

    result = _Interval()
    for specifier in specifiers:
        interval = _specifier_interval(specifier)
        if interval is None:
            return None
        result = _intersect(result, interval)
        if _is_empty(result):
            return None
    return result


def _specifier_interval(specifier: Specifier) -> _Interval | None:
    operator = specifier.operator
    raw_version = specifier.version
    if operator in {"!=", "==="} or "+" in raw_version:
        return None
    wildcard = raw_version.endswith(".*")
    base = raw_version[:-2] if wildcard else raw_version
    try:
        version = Version(base)
    except InvalidVersion:
        return None
    if version.is_prerelease or version.is_devrelease or version.is_postrelease or version.local:
        return None
    if wildcard:
        if operator != "==":
            return None
        return _Interval(lower=version, upper=_next_prefix(version), upper_inclusive=False)
    if operator == "==":
        return _Interval(lower=version, upper=version)
    if operator == ">=":
        return _Interval(lower=version, lower_inclusive=True)
    if operator == ">":
        return _Interval(lower=version, lower_inclusive=False)
    if operator == "<=":
        return _Interval(upper=version, upper_inclusive=True)
    if operator == "<":
        return _Interval(upper=version, upper_inclusive=False)
    if operator == "~=":
        release = version.release
        if len(release) < 2:
            return None
        prefix_length = len(release) - 1
        upper_release = list(release[:prefix_length])
        upper_release[-1] += 1
        return _Interval(
            lower=version,
            upper=Version(".".join(map(str, upper_release))),
            upper_inclusive=False,
        )
    return None


def _next_prefix(version: Version) -> Version:
    release = list(version.release)
    release[-1] += 1
    return Version(".".join(map(str, release)))


def _intersect(left: _Interval, right: _Interval) -> _Interval:
    lower, lower_inclusive = _stricter_lower(left, right)
    upper, upper_inclusive = _stricter_upper(left, right)
    return _Interval(lower, lower_inclusive, upper, upper_inclusive)


def _stricter_lower(left: _Interval, right: _Interval) -> tuple[Version | None, bool]:
    if left.lower is None:
        return right.lower, right.lower_inclusive
    if right.lower is None:
        return left.lower, left.lower_inclusive
    if left.lower > right.lower:
        return left.lower, left.lower_inclusive
    if right.lower > left.lower:
        return right.lower, right.lower_inclusive
    return left.lower, left.lower_inclusive and right.lower_inclusive


def _stricter_upper(left: _Interval, right: _Interval) -> tuple[Version | None, bool]:
    if left.upper is None:
        return right.upper, right.upper_inclusive
    if right.upper is None:
        return left.upper, left.upper_inclusive
    if left.upper < right.upper:
        return left.upper, left.upper_inclusive
    if right.upper < left.upper:
        return right.upper, right.upper_inclusive
    return left.upper, left.upper_inclusive and right.upper_inclusive


def _disjoint(left: _Interval, right: _Interval) -> bool:
    return _upper_before_lower(
        left.upper, left.upper_inclusive, right.lower, right.lower_inclusive
    ) or _upper_before_lower(right.upper, right.upper_inclusive, left.lower, left.lower_inclusive)


def _is_empty(interval: _Interval) -> bool:
    if interval.lower is None or interval.upper is None:
        return False
    if interval.lower > interval.upper:
        return True
    return interval.lower == interval.upper and not (
        interval.lower_inclusive and interval.upper_inclusive
    )


def _upper_before_lower(
    upper: Version | None, upper_inclusive: bool, lower: Version | None, lower_inclusive: bool
) -> bool:
    if upper is None or lower is None:
        return False
    if upper < lower:
        return True
    return upper == lower and not (upper_inclusive and lower_inclusive)


def _is_subset(candidate: _Interval, guide: _Interval) -> bool:
    return _lower_within(candidate, guide) and _upper_within(candidate, guide)


def _lower_within(candidate: _Interval, guide: _Interval) -> bool:
    if guide.lower is None:
        return True
    if candidate.lower is None:
        return False
    if candidate.lower > guide.lower:
        return True
    return candidate.lower == guide.lower and (
        not candidate.lower_inclusive or guide.lower_inclusive
    )


def _upper_within(candidate: _Interval, guide: _Interval) -> bool:
    if guide.upper is None:
        return True
    if candidate.upper is None:
        return False
    if candidate.upper < guide.upper:
        return True
    return candidate.upper == guide.upper and (
        not candidate.upper_inclusive or guide.upper_inclusive
    )
