from __future__ import annotations

import pytest
from packaging.version import Version

from modern_python_guidance.dependency_compat import (
    DependencyContext,
    DependencyFact,
    _check_lock_declarations,
    _Interval,
    _range_relation,
    _stricter_lower,
    _stricter_upper,
    _to_interval,
    _upper_within,
    assess_dependencies,
)


def _context(*facts: DependencyFact) -> DependencyContext:
    grouped: dict[tuple[str, str], tuple[DependencyFact, ...]] = {}
    for fact in facts:
        key = (fact.kind, fact.name)
        grouped[key] = (*grouped.get(key, ()), fact)
    return DependencyContext(facts=grouped)


def test_exact_pydantic_v2_confirms_v2_guide() -> None:
    result = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package", name="Pydantic", version="2.7.4", specifier=None, source="uv.lock"
            )
        ),
    )

    assert result.status == "confirmed"
    assert result.evidence[0].name == "pydantic"


def test_exact_pydantic_v1_is_incompatible_with_v2_guide() -> None:
    result = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="pydantic",
                version="1.10.15",
                specifier=None,
                source="uv.lock",
            )
        ),
    )

    assert result.status == "incompatible"


def test_declared_range_is_confirmed_only_when_it_is_a_subset_of_the_guide() -> None:
    confirmed = assess_dependencies(
        package_requirements=("fastapi>=0.95",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="fastapi",
                version=None,
                specifier=">=0.100,<1",
                source="project.dependencies",
            )
        ),
    )
    overlap = assess_dependencies(
        package_requirements=("fastapi>=0.95",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="fastapi",
                version=None,
                specifier=">=0.90,<1",
                source="project.dependencies",
            )
        ),
    )

    assert confirmed.status == "confirmed"
    assert overlap.status == "unknown"


def test_disjoint_declared_range_is_incompatible() -> None:
    result = assess_dependencies(
        package_requirements=("django>=5.1",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="django",
                version=None,
                specifier="<5",
                source="project.dependencies",
            )
        ),
    )

    assert result.status == "incompatible"


def test_unpinned_or_unsupported_declared_constraints_remain_unknown() -> None:
    unpinned = assess_dependencies(
        package_requirements=("httpx>=0.23",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="httpx",
                version=None,
                specifier=None,
                source="project.dependencies",
            )
        ),
    )
    unsupported = assess_dependencies(
        package_requirements=("httpx>=0.23",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="httpx",
                version=None,
                specifier="!=0.23",
                source="project.dependencies",
            )
        ),
    )

    assert unpinned.status == "unknown"
    assert unsupported.status == "unknown"


def test_impossible_declared_ranges_remain_unknown() -> None:
    for specifier in (">2,<=2", ">=3,<2"):
        result = assess_dependencies(
            package_requirements=("pydantic>=2",),
            tool_requirements=(),
            context=_context(
                DependencyFact(
                    kind="package",
                    name="pydantic",
                    version=None,
                    specifier=specifier,
                    source="project.dependencies",
                )
            ),
        )

        assert result.status == "unknown"


def test_conflicting_exact_lock_versions_remain_unknown() -> None:
    result = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package", name="pydantic", version="1.10", specifier=None, source="uv.lock"
            ),
            DependencyFact(
                kind="package", name="pydantic", version="2.7", specifier=None, source="uv.lock"
            ),
        ),
    )

    assert result.status == "unknown"


def test_optional_dependency_does_not_confirm_a_guide() -> None:
    result = assess_dependencies(
        package_requirements=("sqlalchemy>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="sqlalchemy",
                version=None,
                specifier=">=2",
                source="project.optional-dependencies",
            )
        ),
    )

    assert result.status == "unknown"


def test_override_precedes_conflicting_lock_evidence() -> None:
    result = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package", name="pydantic", version="2.6", specifier=None, source="override"
            ),
            DependencyFact(
                kind="package", name="pydantic", version="1.10", specifier=None, source="uv.lock"
            ),
        ),
    )

    assert result.status == "confirmed"


def test_lock_version_conflicting_with_active_declared_range_is_unknown() -> None:
    result = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(
            DependencyFact(
                kind="package",
                name="pydantic",
                version=None,
                specifier="<2",
                source="project.dependencies",
            ),
            DependencyFact(
                kind="package", name="pydantic", version="2.7.4", specifier=None, source="uv.lock"
            ),
        ),
    )

    assert result.status == "unknown"


def test_tool_requirements_use_the_same_tri_state_logic() -> None:
    confirmed = assess_dependencies(
        package_requirements=(),
        tool_requirements=("pip>=21.3",),
        context=_context(
            DependencyFact(
                kind="tool", name="pip", version="24.1", specifier=None, source="override"
            )
        ),
    )
    unknown = assess_dependencies(
        package_requirements=(),
        tool_requirements=("uv", "ruff"),
        context=_context(
            DependencyFact(
                kind="tool", name="uv", version=None, specifier=None, source="tool-table"
            ),
            DependencyFact(
                kind="tool", name="ruff", version=None, specifier=None, source="tool-table"
            ),
        ),
    )

    assert confirmed.status == "confirmed"
    assert unknown.status == "unknown"


def test_invalid_kinds_and_guide_requirement_are_rejected_or_unknown() -> None:
    with pytest.raises(ValueError, match="Unsupported dependency kind"):
        DependencyFact("runtime", "pydantic", "2.0", None, "override")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported dependency kind"):
        DependencyContext({("runtime", "pydantic"): ()})  # type: ignore[arg-type]

    result = assess_dependencies(
        package_requirements=("not a requirement @@@",),
        tool_requirements=(),
        context=_context(),
    )

    assert result.status == "unknown"
    assert "Invalid guide requirement" in result.reasons[0]


def test_exact_evidence_and_bare_requirements_handle_unusual_inputs_conservatively() -> None:
    invalid_version = assess_dependencies(
        package_requirements=("pydantic>=2",),
        tool_requirements=(),
        context=_context(DependencyFact("package", "pydantic", "not-a-version", None, "override")),
    )
    bare_requirement = assess_dependencies(
        package_requirements=("httpx",),
        tool_requirements=(),
        context=_context(DependencyFact("package", "httpx", None, ">=0.23", "override")),
    )

    assert invalid_version.status == "unknown"
    assert bare_requirement.status == "confirmed"


def test_lock_declaration_validation_rejects_conflicts_and_unsupported_ranges() -> None:
    conflicting_declarations = (
        DependencyFact("package", "pydantic", None, ">=2", "project.dependencies"),
        DependencyFact("package", "pydantic", None, "<2", "project.dependencies"),
        DependencyFact("package", "pydantic", "2.7", None, "uv.lock"),
    )
    unsupported_declaration = (
        DependencyFact("package", "pydantic", None, "!=2.0", "project.dependencies"),
        DependencyFact("package", "pydantic", "2.7", None, "uv.lock"),
    )
    missing_lock_version = (
        DependencyFact("package", "pydantic", None, ">=2", "project.dependencies"),
        DependencyFact("package", "pydantic", None, None, "uv.lock"),
    )

    assert _check_lock_declarations(conflicting_declarations) == "conflicting"
    assert _check_lock_declarations(unsupported_declaration) == "unsupported"
    assert _check_lock_declarations(missing_lock_version) == "conflicting"


def test_interval_helpers_cover_supported_edges_without_overclaiming() -> None:
    assert _to_interval("=>2") is None
    assert _to_interval("") is None
    assert _to_interval("==invalid") is None
    assert _to_interval(">=2.dev1") is None
    assert _to_interval("==2.*") is not None
    assert _to_interval("~=2") is None
    assert _range_relation("==1.*", ">=2") == "disjoint"

    two = Version("2")
    three = Version("3")
    assert _stricter_lower(_Interval(lower=three), _Interval(lower=two)) == (three, True)
    assert _stricter_lower(_Interval(lower=two), _Interval(lower=three)) == (three, True)
    assert _stricter_lower(
        _Interval(lower=two, lower_inclusive=False), _Interval(lower=two, lower_inclusive=True)
    ) == (two, False)
    assert _stricter_upper(_Interval(upper=two), _Interval(upper=three)) == (two, True)
    assert _stricter_upper(_Interval(upper=three), _Interval(upper=two)) == (two, True)
    assert _stricter_upper(
        _Interval(upper=two, upper_inclusive=False), _Interval(upper=two, upper_inclusive=True)
    ) == (two, False)
    assert _upper_within(_Interval(), _Interval(upper=two)) is False
    assert (
        _upper_within(_Interval(upper=two), _Interval(upper=two, upper_inclusive=False)) is False
    )
