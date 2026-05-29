#!/usr/bin/env python3
"""AST-based scorer for mpg effectiveness benchmark V5.

Usage:
    python3 bench/score_v5.py <run_id> [--variant a|b|c] [--format human|json]

Examples:
    python3 bench/score_v5.py 1-v5an --variant a
    python3 bench/score_v5.py 1-v5an --variant a --format json

Metrics:
    v4_compat_score_pct  — MODERN / denominator (V4-compatible)
    strict_modern_pct    — MODERN / (MODERN + OUTDATED)
    inclusive_modern_pct  — (MODERN + VALID_ALT) / (MODERN + VALID_ALT + OUTDATED)

Check function interface (for future mpg check reuse):
    def check_XX(files: list[ParsedFile]) -> CheckResult

Design invariant: this module NEVER executes LLM-generated code.
Only ast.parse(), ast.walk(), and node inspection are used.
compile(), exec(), eval(), importlib are FORBIDDEN on LLM output.

Requires Python 3.12+.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class CheckResult(Enum):
    MODERN = "MODERN"
    OUTDATED = "OUTDATED"
    VALID_ALT = "VALID_ALT"
    NONE = "NONE"
    PARSE_ERROR = "PARSE_ERROR"


class ParsedFile(NamedTuple):
    path: Path
    tree: ast.Module
    aliases: dict[str, str]  # alias -> canonical module (e.g. {"sp": "subprocess"})
    reverse_aliases: dict[str, set[str]]  # module -> {alias, ...}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_file(path: Path) -> ParsedFile | None:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    aliases: dict[str, str] = {}
    reverse: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.asname or a.name
                aliases[name] = a.name
                reverse.setdefault(a.name, set()).add(name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                fqn = f"{mod}.{a.name}" if mod else a.name
                name = a.asname or a.name
                aliases[name] = fqn
                reverse.setdefault(mod, set()).add(name)
                reverse.setdefault(fqn, set()).add(name)

    return ParsedFile(path, tree, aliases, reverse)


def discover_files(root: Path) -> list[Path]:
    py_files = sorted(root.rglob("*.py"))
    return py_files


def parse_all(root: Path) -> list[ParsedFile]:
    parsed = []
    for p in discover_files(root):
        pf = parse_file(p)
        if pf is not None:
            parsed.append(pf)
    return parsed


# ---------------------------------------------------------------------------
# AST query helpers
# ---------------------------------------------------------------------------


def file_imports_module(pf: ParsedFile, module: str) -> bool:
    if module in pf.reverse_aliases:
        return True
    # Check for sub-module imports: "from django.db import models" should match "django"
    return any(key.startswith(module + ".") for key in pf.reverse_aliases)


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _iter_code_nodes(tree: ast.Module):
    for node in ast.walk(tree):
        if _is_docstring(node):
            continue
        yield node


def _is_call_to(node: ast.Call, pf: ParsedFile, module: str, func: str) -> bool:
    """Check if node is a call to module.func, accounting for aliases."""
    target = node.func

    # module.func() style
    if (
        isinstance(target, ast.Attribute)
        and target.attr == func
        and isinstance(target.value, ast.Name)
    ):
        name = target.value.id
        canonical = pf.aliases.get(name, name)
        return canonical == module

    # from module import func; func() style
    if isinstance(target, ast.Name):
        canonical = pf.aliases.get(target.id, "")
        return canonical == f"{module}.{func}"

    return False


def _has_import_of(pf: ParsedFile, full_name: str) -> bool:
    return full_name in pf.aliases.values()


def _has_name_usage(pf: ParsedFile, name: str) -> bool:
    for node in ast.walk(pf.tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
    return False


def _is_annotation_context(node: ast.AST, tree: ast.Module) -> bool:
    """Walk parents to check if this node appears in an annotation position."""
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if field in ("annotation", "returns", "slice") and value is node:
                return True
            if isinstance(value, list) and node in value:
                if isinstance(parent, ast.AnnAssign) and field == "annotation":
                    return True
    return False


# ---------------------------------------------------------------------------
# Check functions: each takes list[ParsedFile] and returns CheckResult
#
# Convention: check OUTDATED first. If both found → OUTDATED (transitional code).
# ---------------------------------------------------------------------------


def check_AS1(files: list[ParsedFile]) -> CheckResult:
    """taskgroup-over-gather: TaskGroup vs asyncio.gather"""
    for pf in files:
        if not file_imports_module(pf, "asyncio"):
            continue
        has_outdated = False
        has_modern = False
        # Collect all local names that resolve to asyncio.TaskGroup
        tg_names = set()
        for alias, canonical in pf.aliases.items():
            if canonical == "asyncio.TaskGroup":
                tg_names.add(alias)
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call) and _is_call_to(node, pf, "asyncio", "gather"):
                has_outdated = True
            if isinstance(node, ast.Attribute) and node.attr == "TaskGroup":
                has_modern = True
            if isinstance(node, ast.Name) and (node.id in tg_names or node.id == "TaskGroup"):
                if node.id in tg_names or _has_import_of(pf, "asyncio.TaskGroup"):
                    has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TC3(files: list[ParsedFile]) -> CheckResult:
    """safe-subprocess: subprocess.run([...]) vs os.system/shell=True"""
    for pf in files:
        if not (file_imports_module(pf, "subprocess") or file_imports_module(pf, "os")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if not isinstance(node, ast.Call):
                continue
            # os.system(...)
            if _is_call_to(node, pf, "os", "system"):
                has_outdated = True
                continue
            # subprocess.run(..., shell=True)
            if _is_call_to(node, pf, "subprocess", "run"):
                for kw in node.keywords:
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        has_outdated = True
                        break
                else:
                    # subprocess.run([...]) — first arg is a list
                    if node.args and isinstance(node.args[0], ast.List):
                        has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_DS2(files: list[ParsedFile]) -> CheckResult:
    """dict-merge-operator: dict | merge vs {**a, **b} / .update()"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            # Outdated: {**a, **b}
            if isinstance(node, ast.Dict):
                star_count = sum(1 for k in node.keys if k is None)
                if star_count >= 2:
                    has_outdated = True
            # Outdated: x.update(...)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
            ):
                has_outdated = True
            # Modern: a | b in non-annotation context
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                # Exclude annotation contexts (type unions: int | str)
                # Check parent: if this BinOp appears in AnnAssign.annotation,
                # function return annotation, or isinstance() call, skip it.
                # We use a heuristic: check if either operand is a Name that
                # looks like a type (starts with uppercase or is a builtin type)
                left_is_type = _looks_like_type(node.left)
                right_is_type = _looks_like_type(node.right)
                if not (left_is_type and right_is_type):
                    has_modern = True

        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


_BUILTIN_TYPES = frozenset(
    {
        "int",
        "str",
        "float",
        "bool",
        "bytes",
        "None",
        "list",
        "dict",
        "set",
        "tuple",
        "type",
    }
)


def _looks_like_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Name):
        return node.id[0].isupper() or node.id in _BUILTIN_TYPES
    if isinstance(node, ast.Attribute):
        return node.attr[0].isupper()
    if isinstance(node, ast.Subscript):
        return _looks_like_type(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _looks_like_type(node.left) and _looks_like_type(node.right)
    return False


# ---------------------------------------------------------------------------
# Stub check functions (to be implemented)
# ---------------------------------------------------------------------------


def check_AS2(files: list[ParsedFile]) -> CheckResult:
    """async-timeout-context: asyncio.timeout vs asyncio.wait_for"""
    for pf in files:
        if not file_imports_module(pf, "asyncio"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call) and _is_call_to(node, pf, "asyncio", "wait_for"):
                has_outdated = True
            if isinstance(node, ast.Call) and _is_call_to(node, pf, "asyncio", "timeout"):
                has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_AS3(files: list[ParsedFile]) -> CheckResult:
    """exception-groups: except* vs except Exception with ExceptionGroup"""
    for pf in files:
        has_outdated = False
        has_modern = False
        has_valid_alt = False
        has_taskgroup = False
        has_per_task_try = False

        for node in ast.walk(pf.tree):
            if isinstance(node, ast.TryStar):
                has_modern = True
            if isinstance(node, ast.Attribute) and node.attr == "TaskGroup":
                has_taskgroup = True
            if isinstance(node, ast.Name) and node.id == "TaskGroup":
                has_taskgroup = True

        # Per-task try/except inside TaskGroup = VALID_ALT
        if has_taskgroup and not has_modern:
            for node in ast.walk(pf.tree):
                if isinstance(node, ast.Try):
                    has_per_task_try = True
            if has_per_task_try:
                has_valid_alt = True

        # except Exception with ExceptionGroup mentioned = OUTDATED
        if not has_modern and not has_valid_alt:
            for node in _iter_code_nodes(pf.tree):
                if isinstance(node, ast.ExceptHandler) and (
                    node.type
                    and isinstance(node.type, ast.Name)
                    and node.type.id == "Exception"
                    and has_taskgroup
                ):
                    has_outdated = True

        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
        if has_valid_alt:
            return CheckResult.VALID_ALT
    return CheckResult.NONE


def check_DS1(files: list[ParsedFile]) -> CheckResult:
    """dataclass-modern: @dataclass(slots=True) vs plain @dataclass"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    func = dec.func
                    if (isinstance(func, ast.Name) and func.id == "dataclass") or (
                        isinstance(func, ast.Attribute) and func.attr == "dataclass"
                    ):
                        for kw in dec.keywords:
                            if (
                                kw.arg == "slots"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                            ):
                                has_modern = True
                        if not has_modern:
                            has_outdated = True
                elif (isinstance(dec, ast.Name) and dec.id == "dataclass") or (
                    isinstance(dec, ast.Attribute) and dec.attr == "dataclass"
                ):
                    has_outdated = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_DS3(files: list[ParsedFile]) -> CheckResult:
    """match-case-patterns: match/case vs if/elif isinstance chains"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Match):
                has_modern = True
            if isinstance(node, ast.If) and node.orelse:
                # Check for isinstance chain: if isinstance(...) elif isinstance(...)
                if _is_isinstance_call(node.test):
                    for elif_node in node.orelse:
                        if isinstance(elif_node, ast.If) and _is_isinstance_call(elif_node.test):
                            has_outdated = True
                            break
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def _is_isinstance_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
    )


def check_FA1(files: list[ParsedFile]) -> CheckResult:
    """fastapi-lifespan: lifespan context manager vs on_event()"""
    for pf in files:
        if not (file_imports_module(pf, "fastapi") or _has_name_usage(pf, "FastAPI")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "on_event"
            ):
                has_outdated = True
            if isinstance(node, ast.Name) and node.id == "lifespan":
                has_modern = True
            if isinstance(node, ast.keyword) and node.arg == "lifespan":
                has_modern = True
        # Also check for lifespan keyword in FastAPI() constructor
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "lifespan":
                        has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_FA2(files: list[ParsedFile]) -> CheckResult:
    """fastapi-annotated-depends: Annotated[X, Depends()] vs = Depends()"""
    for pf in files:
        if not (file_imports_module(pf, "fastapi") or _has_import_of(pf, "fastapi.Depends")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Annotated"
            ):
                has_modern = True
        if not has_modern:
            # Check for = Depends(...) in function params
            for node in _iter_code_nodes(pf.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if default and isinstance(default, ast.Call):
                            if isinstance(default.func, ast.Name) and default.func.id == "Depends":
                                has_outdated = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_FA3(files: list[ParsedFile]) -> CheckResult:
    """fastapi-typed-state: lifespan yield dict vs app.state/request.state"""
    for pf in files:
        if not (file_imports_module(pf, "fastapi") or _has_name_usage(pf, "FastAPI")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr == "state":
                if isinstance(node.value, ast.Attribute) or (
                    isinstance(node.value, ast.Name) and node.value.id in ("app", "request")
                ):
                    has_outdated = True
            # yield {...} inside a function with lifespan in its name or decorators
            if isinstance(node, ast.Yield) and isinstance(node.value, ast.Dict):
                has_modern = True
        # Check for lifespan + yield dict combination
        for node in ast.walk(pf.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "lifespan" in node.name:
                    for child in ast.walk(node):
                        if isinstance(child, ast.Yield) and isinstance(child.value, ast.Dict):
                            has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_HX1(files: list[ParsedFile]) -> CheckResult:
    """httpx-async-client-reuse: AsyncClient context manager vs per-request calls"""
    for pf in files:
        if not file_imports_module(pf, "httpx"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            # Per-request: httpx.get(), httpx.post() etc
            if isinstance(node, ast.Call):
                for method in ("get", "post", "head", "put", "delete"):
                    if _is_call_to(node, pf, "httpx", method):
                        has_outdated = True
            # Modern: AsyncClient usage
            if isinstance(node, ast.Name) and node.id == "AsyncClient":
                has_modern = True
            if isinstance(node, ast.Attribute) and node.attr == "AsyncClient":
                has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_HX2(files: list[ParsedFile]) -> CheckResult:
    """httpx-streaming: .stream() / aiter_bytes / aiter_lines / aiter_text"""
    for pf in files:
        if not file_imports_module(pf, "httpx"):
            continue
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr in (
                "stream",
                "aiter_bytes",
                "aiter_lines",
                "aiter_text",
            ):
                return CheckResult.MODERN
    return CheckResult.NONE


def check_PD1(files: list[ParsedFile]) -> CheckResult:
    """pydantic-v2-config: model_config = ConfigDict() vs class Config:"""
    for pf in files:
        if not (file_imports_module(pf, "pydantic") or _has_name_usage(pf, "BaseModel")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.ClassDef) and node.name == "Config":
                has_outdated = True
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_PD2(files: list[ParsedFile]) -> CheckResult:
    """pydantic-v2-model-api: model_validate/model_dump vs parse_obj/.dict()"""
    for pf in files:
        if not (file_imports_module(pf, "pydantic") or _has_name_usage(pf, "BaseModel")):
            continue
        has_outdated = False
        has_modern = False
        outdated_methods = {"parse_obj", "parse_raw", "dict", "json", "schema"}
        modern_methods = {
            "model_validate",
            "model_dump",
            "model_dump_json",
            "model_json_schema",
            "model_validate_json",
        }
        for node in _iter_code_nodes(pf.tree):
            # Only match method CALLS (.dict() not .dict attribute access)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in outdated_methods:
                    has_outdated = True
                if node.func.attr in modern_methods:
                    has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_PD3(files: list[ParsedFile]) -> CheckResult:
    """pydantic-v2-serialization: @field_serializer/@model_serializer vs json_encoders"""
    for pf in files:
        if not (file_imports_module(pf, "pydantic") or _has_name_usage(pf, "BaseModel")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Name) and node.id == "json_encoders":
                has_outdated = True
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "json_encoders":
                        has_outdated = True
            if isinstance(node, ast.Name) and node.id in ("field_serializer", "model_serializer"):
                has_modern = True
            if isinstance(node, ast.Attribute) and node.attr in (
                "field_serializer",
                "model_serializer",
            ):
                has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_PD4(files: list[ParsedFile]) -> CheckResult:
    """pydantic-v2-validators: @field_validator/@model_validator vs @validator/@root_validator"""
    for pf in files:
        if not (file_imports_module(pf, "pydantic") or _has_name_usage(pf, "BaseModel")):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Name) and node.id in ("validator", "root_validator"):
                has_outdated = True
            if isinstance(node, ast.Name) and node.id in ("field_validator", "model_validator"):
                has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_SA1(files: list[ParsedFile]) -> CheckResult:
    """sqlalchemy-2-style: select() vs .query()"""
    for pf in files:
        if not file_imports_module(pf, "sqlalchemy"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr == "query":
                has_outdated = True
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "select":
                    has_modern = True
                if _is_call_to(node, pf, "sqlalchemy", "select"):
                    has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_SA2(files: list[ParsedFile]) -> CheckResult:
    """sqlalchemy-async-session: async vs sync (VALID_ALT for sync 2.0)."""
    for pf in files:
        if not file_imports_module(pf, "sqlalchemy"):
            continue
        has_modern = False
        has_valid_alt = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Name) and node.id in (
                "create_async_engine",
                "async_sessionmaker",
                "AsyncSession",
            ):
                has_modern = True
            if isinstance(node, ast.Attribute) and node.attr in (
                "create_async_engine",
                "async_sessionmaker",
                "AsyncSession",
            ):
                has_modern = True
        if not has_modern:
            for node in _iter_code_nodes(pf.tree):
                if isinstance(node, ast.Call) and ((
                    isinstance(node.func, ast.Name) and node.func.id == "create_engine"
                ) or _is_call_to(node, pf, "sqlalchemy", "create_engine")):
                    has_valid_alt = True
        # No engine creation at all → NONE (not OUTDATED)
        if has_modern:
            return CheckResult.MODERN
        if has_valid_alt:
            return CheckResult.VALID_ALT
    return CheckResult.NONE


def check_SA3(files: list[ParsedFile]) -> CheckResult:
    """sqlalchemy-mapped-column: Mapped[]/mapped_column() vs Column()"""
    for pf in files:
        if not file_imports_module(pf, "sqlalchemy"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "Column":
                    has_outdated = True
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "mapped_column":
                    has_modern = True
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Mapped"
            ):
                has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_SL1(files: list[ParsedFile]) -> CheckResult:
    """datetime-utc: datetime.now(UTC) vs .utcnow()"""
    for pf in files:
        if not file_imports_module(pf, "datetime"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr in ("utcnow", "utcfromtimestamp"):
                has_outdated = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
            ):
                for arg in node.args:
                    if _mentions_utc(arg):
                        has_modern = True
                for kw in node.keywords:
                    if kw.arg == "tz" and _mentions_utc(kw.value):
                        has_modern = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "fromtimestamp"
            ):
                for kw in node.keywords:
                    if kw.arg == "tz":
                        has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def _mentions_utc(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr in ("utc", "UTC"):
        return True
    return bool(isinstance(node, ast.Name) and node.id in ("UTC", "utc"))


def check_SL2(files: list[ParsedFile]) -> CheckResult:
    """pathlib-over-os-path: Path() vs os.path.join() etc"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                if (
                    isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "os"
                    and node.value.attr == "path"
                ) and node.attr in ("join", "exists", "dirname", "basename", "splitext"):
                    has_outdated = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Path"
            ):
                has_modern = True
            if _has_import_of(pf, "pathlib.Path") or _has_import_of(pf, "pathlib"):
                has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_SL3(files: list[ParsedFile]) -> CheckResult:
    """removeprefix/removesuffix vs lstrip/rstrip/[len():]."""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr in ("lstrip", "rstrip"):
                has_outdated = True
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
                # [len(prefix):] pattern
                s = node.slice
                if (
                    s.lower
                    and isinstance(s.lower, ast.Call)
                    and isinstance(s.lower.func, ast.Name)
                    and s.lower.func.id == "len"
                ):
                    has_outdated = True
            if isinstance(node, ast.Attribute) and node.attr in ("removeprefix", "removesuffix"):
                has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_SL4(files: list[ParsedFile]) -> CheckResult:
    """tomllib-builtin: import tomllib vs import toml/tomli"""
    for pf in files:
        has_outdated = False
        has_modern = False
        if (
            _has_import_of(pf, "toml")
            or file_imports_module(pf, "toml")
            or file_imports_module(pf, "tomli")
        ):
            has_outdated = True
        if file_imports_module(pf, "tomllib") or _has_import_of(pf, "tomllib"):
            has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TC1(files: list[ParsedFile]) -> CheckResult:
    """pyproject-toml-over-setup: pyproject.toml [project] vs setup.py"""
    # Non-AST: check for file existence and content
    if not files:
        return CheckResult.NONE
    base = files[0].path.parent
    if base.name == "src":
        base = base.parent
    has_outdated = False
    has_modern = False
    setup_py = base / "setup.py"
    if setup_py.is_file():
        try:
            tree = ast.parse(setup_py.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "setup"
                ):
                    has_outdated = True
        except SyntaxError:
            pass
    pyproject = base / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            if "project" in data:
                has_modern = True
        except Exception:
            pass
    if has_outdated:
        return CheckResult.OUTDATED
    if has_modern:
        return CheckResult.MODERN
    return CheckResult.NONE


def check_TC2(files: list[ParsedFile]) -> CheckResult:
    """ruff-over-flake8: [tool.ruff] vs [tool.flake8]/[tool.black]/[tool.isort]"""
    if not files:
        return CheckResult.NONE
    base = files[0].path.parent
    if base.name == "src":
        base = base.parent
    pyproject = base / "pyproject.toml"
    if not pyproject.is_file():
        return CheckResult.NONE
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        tool = data.get("tool", {})
        has_outdated = any(k in tool for k in ("flake8", "black", "isort"))
        has_modern = "ruff" in tool
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    except Exception:
        pass
    return CheckResult.NONE


def check_TC4(files: list[ParsedFile]) -> CheckResult:
    """no-pickle: absence of pickle.load/dump/loads/dumps"""
    for pf in files:
        pickle_funcs = {"load", "dump", "loads", "dumps"}
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in pickle_funcs:
                    if isinstance(node.func.value, ast.Name):
                        canonical = pf.aliases.get(node.func.value.id, node.func.value.id)
                        if canonical == "pickle":
                            return CheckResult.OUTDATED
    return CheckResult.MODERN


def check_TC5(files: list[ParsedFile]) -> CheckResult:
    """uv-over-pip: uv usage in pyproject.toml/Makefile/shell (informational)"""
    if not files:
        return CheckResult.NONE
    base = files[0].path.parent
    if base.name == "src":
        base = base.parent
    uv_pattern = re.compile(r"uv\s+(pip|add|run|sync)")
    for candidate in [base / "pyproject.toml", base / "Makefile", *list(base.glob("*.sh"))]:
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
                if uv_pattern.search(text):
                    return CheckResult.MODERN
            except Exception:
                pass
    return CheckResult.NONE


def check_TY1(files: list[ParsedFile]) -> CheckResult:
    """use-builtin-generics: list[] vs typing.List[]"""
    for pf in files:
        has_outdated = False
        has_modern = False
        typing_generics = {"List", "Dict", "Set", "Tuple"}
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if (
                    isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "typing"
                    and node.value.attr in typing_generics
                ):
                    has_outdated = True
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                if node.value.id in typing_generics and _has_import_of(
                    pf, f"typing.{node.value.id}"
                ):
                    has_outdated = True
                if node.value.id in ("list", "dict", "set", "tuple"):
                    has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TY2(files: list[ParsedFile]) -> CheckResult:
    """union-syntax: X | None vs Optional[X] / Union[X, Y]"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                if node.value.id in ("Optional", "Union"):
                    has_outdated = True
            # X | None in annotations
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                if _looks_like_type(node.left) and _looks_like_type(node.right):
                    has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TY3(files: list[ParsedFile]) -> CheckResult:
    """type-parameter-syntax: class Foo[T]: vs TypeVar('T')"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "TypeVar"
            ):
                has_outdated = True
            if isinstance(node, ast.ClassDef) and getattr(node, "type_params", None):
                has_modern = True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(
                node, "type_params", None
            ):
                has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TY4(files: list[ParsedFile]) -> CheckResult:
    """override-decorator: @override"""
    for pf in files:
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "override":
                        return CheckResult.MODERN
    return CheckResult.NONE


def check_TY5(files: list[ParsedFile]) -> CheckResult:
    """paramspec-decorators: ParamSpec vs *args: Any, **kwargs: Any"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ParamSpec"
            ):
                has_modern = True
            if isinstance(node, ast.Name) and node.id == "ParamSpec":
                has_modern = True
        if not has_modern:
            for node in _iter_code_nodes(pf.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    if args.vararg and args.kwarg:
                        vararg_ann = args.vararg.annotation
                        kwarg_ann = args.kwarg.annotation
                        if (
                            vararg_ann
                            and isinstance(vararg_ann, ast.Name)
                            and vararg_ann.id == "Any"
                            and kwarg_ann
                            and isinstance(kwarg_ann, ast.Name)
                            and kwarg_ann.id == "Any"
                        ):
                            has_outdated = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_TY6(files: list[ParsedFile]) -> CheckResult:
    """typeis-vs-typeguard: TypeIs vs TypeGuard (VALID_ALT for TypeGuard)"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                if node.value.id == "TypeGuard":
                    has_outdated = True
                if node.value.id == "TypeIs":
                    has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.VALID_ALT
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_DJ1(files: list[ParsedFile]) -> CheckResult:
    """django-json-field: models.JSONField vs contrib.postgres JSONField"""
    for pf in files:
        if not file_imports_module(pf, "django"):
            continue
        has_outdated = False
        has_modern = False
        if _has_import_of(pf, "django.contrib.postgres.fields.JSONField"):
            has_outdated = True
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Attribute) and node.attr == "JSONField":
                if isinstance(node.value, ast.Name) and node.value.id == "models":
                    has_modern = True
        if _has_import_of(pf, "django.db.models.JSONField"):
            has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_DJ2(files: list[ParsedFile]) -> CheckResult:
    """django-check-constraints: condition= vs check="""
    for pf in files:
        if not _has_name_usage(pf, "CheckConstraint"):
            continue
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "check":
                        has_outdated = True
                    if kw.arg == "condition":
                        has_modern = True
        if has_outdated:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_DJ3(files: list[ParsedFile]) -> CheckResult:
    """django-async-views: native async (.aget/.afirst/async for) vs sync_to_async wrapper"""
    for pf in files:
        if not (file_imports_module(pf, "django") or file_imports_module(pf, "asgiref")):
            continue
        has_sync_to_async = False
        has_native_async = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "sync_to_async"
            ):
                has_sync_to_async = True
            if isinstance(node, ast.Attribute) and node.attr in ("aget", "afirst", "acount"):
                has_native_async = True
            if isinstance(node, ast.AsyncFor):
                has_native_async = True
        if has_sync_to_async and not has_native_async:
            return CheckResult.OUTDATED
        if has_native_async:
            return CheckResult.MODERN
    return CheckResult.NONE


def check_PT1(files: list[ParsedFile]) -> CheckResult:
    """pytest-parametrize: @pytest.mark.parametrize"""
    for pf in files:
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr == "parametrize":
                            return CheckResult.MODERN
    return CheckResult.NONE


def check_PT2(files: list[ParsedFile]) -> CheckResult:
    """pytest-raises-match: pytest.raises(..., match=) vs bare pytest.raises"""
    for pf in files:
        has_modern = False
        has_bare = False
        for node in _iter_code_nodes(pf.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "raises"
            ):
                has_match = any(kw.arg == "match" for kw in node.keywords)
                if has_match:
                    has_modern = True
                else:
                    has_bare = True
        # V4-compatible: match= present → MODERN, regardless of bare raises
        if has_modern:
            return CheckResult.MODERN
        if has_bare:
            return CheckResult.OUTDATED
    return CheckResult.NONE


def check_PT3(files: list[ParsedFile]) -> CheckResult:
    """pytest-tmp-path: tmp_path vs tmpdir"""
    for pf in files:
        has_outdated = False
        has_modern = False
        for node in _iter_code_nodes(pf.tree):
            if isinstance(node, ast.Name) and node.id == "tmpdir":
                has_outdated = True
            if isinstance(node, ast.Name) and node.id == "tmp_path":
                has_modern = True
        if has_outdated and not has_modern:
            return CheckResult.OUTDATED
        if has_modern:
            return CheckResult.MODERN
    return CheckResult.NONE


# ---------------------------------------------------------------------------
# Item registry and variant manifests
# ---------------------------------------------------------------------------

CHECKS: dict[str, callable] = {
    "AS1": check_AS1,
    "AS2": check_AS2,
    "AS3": check_AS3,
    "DS1": check_DS1,
    "DS2": check_DS2,
    "DS3": check_DS3,
    "FA1": check_FA1,
    "FA2": check_FA2,
    "FA3": check_FA3,
    "HX1": check_HX1,
    "HX2": check_HX2,
    "PD1": check_PD1,
    "PD2": check_PD2,
    "PD3": check_PD3,
    "PD4": check_PD4,
    "SA1": check_SA1,
    "SA2": check_SA2,
    "SA3": check_SA3,
    "SL1": check_SL1,
    "SL2": check_SL2,
    "SL3": check_SL3,
    "SL4": check_SL4,
    "TC1": check_TC1,
    "TC2": check_TC2,
    "TC3": check_TC3,
    "TC4": check_TC4,
    "TC5": check_TC5,
    "TY1": check_TY1,
    "TY2": check_TY2,
    "TY3": check_TY3,
    "TY4": check_TY4,
    "TY5": check_TY5,
    "TY6": check_TY6,
    "DJ1": check_DJ1,
    "DJ2": check_DJ2,
    "DJ3": check_DJ3,
    "PT1": check_PT1,
    "PT2": check_PT2,
    "PT3": check_PT3,
}

ITEM_LABELS: dict[str, str] = {
    "AS1": "taskgroup-over-gather",
    "AS2": "async-timeout-context",
    "AS3": "exception-groups",
    "DS1": "dataclass-modern",
    "DS2": "dict-merge-operator",
    "DS3": "match-case-patterns",
    "FA1": "fastapi-lifespan",
    "FA2": "fastapi-annotated-depends",
    "FA3": "fastapi-typed-state",
    "HX1": "httpx-async-client-reuse",
    "HX2": "httpx-streaming",
    "PD1": "pydantic-v2-config",
    "PD2": "pydantic-v2-model-api",
    "PD3": "pydantic-v2-serialization",
    "PD4": "pydantic-v2-validators",
    "SA1": "sqlalchemy-2-style",
    "SA2": "sqlalchemy-async-session",
    "SA3": "sqlalchemy-mapped-column",
    "SL1": "datetime-utc",
    "SL2": "pathlib-over-os-path",
    "SL3": "removeprefix-removesuffix",
    "SL4": "tomllib-builtin",
    "TC1": "pyproject-toml-over-setup",
    "TC2": "ruff-over-flake8",
    "TC3": "safe-subprocess",
    "TC4": "no-pickle",
    "TC5": "uv-over-pip",
    "TY1": "use-builtin-generics",
    "TY2": "union-syntax",
    "TY3": "type-parameter-syntax",
    "TY4": "override-decorator",
    "TY5": "paramspec-decorators",
    "TY6": "typeis-vs-typeguard",
    "DJ1": "django-json-field",
    "DJ2": "django-check-constraints",
    "DJ3": "django-async-views",
    "PT1": "pytest-parametrize",
    "PT2": "pytest-raises-match",
    "PT3": "pytest-tmp-path",
}

VARIANT_A_SCORED = [
    "AS1",
    "AS2",
    "AS3",
    "DS1",
    "DS2",
    "DS3",
    "FA1",
    "FA2",
    "FA3",
    "HX1",
    "HX2",
    "PD1",
    "PD2",
    "PD3",
    "PD4",
    "SA1",
    "SA2",
    "SA3",
    "SL1",
    "SL2",
    "SL3",
    "SL4",
    "TC1",
    "TC2",
    "TC3",
    "TC4",
    "TY1",
    "TY2",
    "TY3",
    "TY4",
    "TY5",
    "TY6",
]
VARIANT_A_INFO = ["TC5"]

VARIANT_B_SCORED = ["DJ1", "DJ2", "DJ3"]
VARIANT_C_SCORED = ["PT1", "PT2", "PT3"]

VARIANT_MANIFESTS = {
    "a": (VARIANT_A_SCORED, VARIANT_A_INFO),
    "b": (VARIANT_B_SCORED, []),
    "c": (VARIANT_C_SCORED, []),
}


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


def score_session(session_dir: Path, variant: str) -> dict:
    scored_items, info_items = VARIANT_MANIFESTS[variant]

    # Discover source directory
    src_dir = session_dir / "src"
    if not src_dir.is_dir():
        if variant == "b":
            src_dir = session_dir / "myapp"
        elif variant == "c":
            src_dir = session_dir
        if not src_dir.is_dir():
            src_dir = session_dir

    files = parse_all(src_dir)

    # For items that need pyproject.toml / setup.py, look in parent

    results = {}
    for item_id in scored_items + info_items:
        check_fn = CHECKS[item_id]
        result = check_fn(files)
        results[item_id] = result

    # Aggregate
    modern = sum(1 for i in scored_items if results[i] == CheckResult.MODERN)
    valid_alt = sum(1 for i in scored_items if results[i] == CheckResult.VALID_ALT)
    outdated = sum(1 for i in scored_items if results[i] == CheckResult.OUTDATED)
    none_count = sum(1 for i in scored_items if results[i] == CheckResult.NONE)
    parse_error = sum(1 for i in scored_items if results[i] == CheckResult.PARSE_ERROR)
    denominator = len(scored_items)

    strict_denom = modern + outdated
    inclusive_denom = modern + valid_alt + outdated
    strict_pct = (modern / strict_denom * 100) if strict_denom > 0 else 0.0
    inclusive_pct = ((modern + valid_alt) / inclusive_denom * 100) if inclusive_denom > 0 else 0.0
    v4_compat_pct = (modern / denominator * 100) if denominator > 0 else 0.0

    return {
        "variant": variant,
        "denominator": denominator,
        "modern": modern,
        "valid_alt": valid_alt,
        "outdated": outdated,
        "none": none_count,
        "parse_error": parse_error,
        "v4_compat_score_pct": round(v4_compat_pct, 1),
        "strict_modern_pct": round(strict_pct, 1),
        "inclusive_modern_pct": round(inclusive_pct, 1),
        "items": {
            item_id: {
                "result": results[item_id].value,
                "label": ITEM_LABELS.get(item_id, "unknown"),
                "scored": item_id in scored_items,
            }
            for item_id in scored_items + info_items
        },
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def print_human(session_name: str, data: dict) -> None:
    variant_labels = {"a": "A (FastAPI ecosystem)", "b": "B (Django)", "c": "C (pytest)"}
    v = data["variant"]
    print(f"  Variant: {variant_labels.get(v, v)}")
    print(f"  Score: {data['modern']} / {data['denominator']} ({data['v4_compat_score_pct']}%)")
    print(
        f"  Modern: {data['modern']}  VALID_ALT: {data['valid_alt']}  "
        f"Outdated: {data['outdated']}  None: {data['none']}  ParseError: {data['parse_error']}"
    )
    print(
        f"  Strict modern: {data['strict_modern_pct']}%  "
        f"Inclusive: {data['inclusive_modern_pct']}%"
    )
    print()

    current_cat = ""
    for item_id, item_data in data["items"].items():
        cat = item_id.rstrip("0123456789")
        if cat != current_cat:
            current_cat = cat
            print()
        result = item_data["result"]
        marker = {
            "MODERN": "✓",
            "OUTDATED": "✗",
            "VALID_ALT": "≈",
            "NONE": "·",
            "PARSE_ERROR": "!",
        }
        tag = "[info]" if not item_data["scored"] else ""
        print(f"  {marker.get(result, '?')} {item_id}: {result} ({item_data['label']}) {tag}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="V5 AST-based benchmark scorer")
    parser.add_argument("run_id", help="Run ID (results directory suffix)")
    parser.add_argument("--variant", default="a", choices=["a", "b", "c"])
    parser.add_argument(
        "--format", default="human", choices=["human", "json"], dest="output_format"
    )
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent.parent
    results_dir = repo_dir / "results" / f"run-{args.run_id}"
    if not results_dir.is_dir():
        print(f"ERROR: Results not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    variant_labels = {
        "a": "A (FastAPI ecosystem)",
        "b": "B (Django)",
        "c": "C (pytest)",
    }
    v_label = variant_labels.get(args.variant, args.variant)
    print(f"=== V5 Scoring: Variant {v_label}, Run {args.run_id} ===")
    print()

    output = {}
    for session_name in ("control", "treatment"):
        session_dir = results_dir / session_name
        if not session_dir.is_dir():
            print(f"  [{session_name}] Directory not found, skipping.")
            continue
        data = score_session(session_dir, args.variant)
        output[session_name] = data

        if args.output_format == "human":
            print(f"--- {session_name.title()} ---")
            print_human(session_name, data)

    if args.output_format == "json":
        print(
            json.dumps(
                {"run_id": args.run_id, "variant": args.variant, "sessions": output}, indent=2
            )
        )


if __name__ == "__main__":
    main()
