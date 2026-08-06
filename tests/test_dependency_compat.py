from __future__ import annotations

from modern_python_guidance.dependency_compat import (
    DependencyContext,
    DependencyFact,
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
