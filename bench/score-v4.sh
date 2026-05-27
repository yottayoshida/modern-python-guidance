#!/usr/bin/env bash
set -euo pipefail

# Automated scorer for effectiveness benchmark V4
# 39/39 guide coverage, fixed denominator, 3-variant system
#
# Usage: ./bench/score-v4.sh <run_id> [--variant a|b|c]
#
# Variants:
#   a — FastAPI + async ecosystem (32 scored + 1 informational)
#   b — Django (3 scored)
#   c — pytest (3 scored)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:?Usage: $0 <run_id> [--variant a|b|c]}"
shift
VARIANT="${VARIANT:-a}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --variant) VARIANT="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"
if [ ! -d "$RESULTS_DIR" ]; then
    echo "ERROR: Results not found: $RESULTS_DIR" >&2
    exit 1
fi

# --- Helpers ---

file_has() {
    local file="$1" pattern="$2"
    [ -f "$file" ] && grep -qE "$pattern" "$file" 2>/dev/null
}

file_has_stripped() {
    local file="$1" pattern="$2"
    [ -f "$file" ] && grep -v '^\s*#' "$file" | grep -qE "$pattern" 2>/dev/null
}

# --- Check functions ---
# Each returns: MODERN, OUTDATED, or NONE
# Rule: check OUTDATED first. If both found → OUTDATED (V-009: transitional code)
# All patterns use ERE (grep -E): | for alternation, \( for literal paren, \[ for literal bracket

check_AS1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'asyncio' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'asyncio\.gather\(' && has_outdated=true
        file_has_stripped "$f" 'TaskGroup' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_AS2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'asyncio' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'asyncio\.wait_for\(' && has_outdated=true
        file_has_stripped "$f" 'asyncio\.timeout\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_AS3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'except Exception' && file_has_stripped "$f" 'TaskGroup|ExceptionGroup' && has_outdated=true
        file_has_stripped "$f" 'except[*]' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DS1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'dataclass' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '@dataclass\(.*slots\s*=\s*True' && has_modern=true
        if ! $has_modern && file_has_stripped "$f" '@dataclass'; then has_outdated=true; fi
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DS2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\{\s*\*\*.*\*\*' && has_outdated=true
        file_has_stripped "$f" '\.update\(' && has_outdated=true
        grep -v '^\s*#' "$f" | grep -vE ':\s|->|def |class ' | grep -qE '[a-zA-Z_]+\s*\|\s*[a-zA-Z_]+' 2>/dev/null && file_has "$f" 'dict|Dict' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DS3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'if isinstance.*elif isinstance' && has_outdated=true
        file_has_stripped "$f" '^\s*match ' && file_has_stripped "$f" '^\s*case ' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_FA1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'fastapi|FastAPI' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'on_event\(' && has_outdated=true
        file_has_stripped "$f" 'lifespan' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_FA2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'Depends|fastapi' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'Annotated\[' && has_modern=true
        if ! $has_modern && file_has_stripped "$f" '=\s*Depends\('; then has_outdated=true; fi
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_FA3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'FastAPI|fastapi' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'app\.state\.|request\.state\.' && has_outdated=true
        file_has_stripped "$f" 'yield\s*\{' && file_has_stripped "$f" 'lifespan' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_HX1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'httpx' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'httpx\.(get|post|head|put|delete)\(' && has_outdated=true
        file_has_stripped "$f" 'AsyncClient' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_HX2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'httpx' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\.stream\(|aiter_bytes|aiter_lines|aiter_text' && has_modern=true
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PD1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'pydantic|BaseModel' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'class Config:' && has_outdated=true
        file_has_stripped "$f" 'model_config\s*=' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PD2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'pydantic|BaseModel' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\.parse_obj\(|\.parse_raw\(|\.dict\(\)|\.json\(\)|\.schema\(\)' && has_outdated=true
        file_has_stripped "$f" '\.model_validate\(|\.model_dump\(|\.model_dump_json\(|\.model_json_schema\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PD3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'pydantic|BaseModel' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'json_encoders' && has_outdated=true
        file_has_stripped "$f" '@field_serializer\(|@model_serializer\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PD4() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'pydantic|BaseModel' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '@validator\(|@root_validator' && has_outdated=true
        file_has_stripped "$f" '@field_validator\(|@model_validator\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SA1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'sqlalchemy' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\.query\(' && has_outdated=true
        file_has_stripped "$f" '\bselect\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SA2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'sqlalchemy' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'create_async_engine\(|async_sessionmaker\(|AsyncSession' && has_modern=true
        if ! $has_modern && file_has_stripped "$f" 'create_engine\('; then has_outdated=true; fi
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SA3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'sqlalchemy' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'Column\(' && has_outdated=true
        file_has_stripped "$f" 'mapped_column\(|Mapped\[' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SL1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'datetime' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\.utcnow\(\)|\.utcfromtimestamp\(' && has_outdated=true
        file_has_stripped "$f" 'datetime\.now\(.*UTC|datetime\.now\(.*timezone\.utc|\.fromtimestamp\(.*tz=' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SL2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'os\.path\.(join|exists|dirname|basename|splitext)\(' && has_outdated=true
        file_has_stripped "$f" 'Path\(|from pathlib' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SL3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\.lstrip\(|\.rstrip\(|\[len\(' && has_outdated=true
        file_has_stripped "$f" '\.removeprefix\(|\.removesuffix\(' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_SL4() {
    local d="$1"
    local f
    for f in "$d"/*.py "$d"/../*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'import toml$|from toml |import tomli$|from tomli ' && has_outdated=true
        file_has_stripped "$f" 'import tomllib|from tomllib|tomllib\.' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TC1() {
    local d="$1"
    local base
    base="$(dirname "$d")"
    local has_outdated=false has_modern=false
    [ -f "$base/setup.py" ] && file_has "$base/setup.py" 'setup\(' && has_outdated=true
    [ -f "$base/pyproject.toml" ] && file_has "$base/pyproject.toml" '\[project\]' && has_modern=true
    if $has_outdated; then echo "OUTDATED"; return; fi
    if $has_modern; then echo "MODERN"; return; fi
    echo "NONE"
}

check_TC2() {
    local d="$1"
    local base
    base="$(dirname "$d")"
    local pyproject="$base/pyproject.toml"
    [ -f "$pyproject" ] || { echo "NONE"; return; }
    local has_outdated=false has_modern=false
    file_has "$pyproject" '\[tool\.flake8\]|\[tool\.black\]|\[tool\.isort\]' && has_outdated=true
    file_has "$pyproject" '\[tool\.ruff' && has_modern=true
    if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
    if $has_modern; then echo "MODERN"; return; fi
    echo "NONE"
}

check_TC3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'subprocess|os\.system' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'os\.system\(|shell\s*=\s*True' && has_outdated=true
        file_has_stripped "$f" 'subprocess\.run\(\s*\[' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TC4() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false
        file_has_stripped "$f" 'pickle\.load\(|pickle\.dump\(|pickle\.loads\(|pickle\.dumps\(' && has_outdated=true
        if $has_outdated; then echo "OUTDATED"; return; fi
    done
    echo "MODERN"
}

check_TC5() {
    local d="$1"
    local base
    base="$(dirname "$d")"
    local has_modern=false
    for f in "$base/pyproject.toml" "$base"/Makefile "$base"/*.sh "$base"/.github/workflows/*.yml; do
        [ -f "$f" ] || continue
        file_has "$f" 'uv pip|uv add|uv run|uv sync' && has_modern=true
    done
    if $has_modern; then echo "MODERN"; else echo "NONE"; fi
}

check_TY1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'from typing import.*(List|Dict|Set|Tuple)|typing\.(List|Dict|Set|Tuple)\[' && has_outdated=true
        file_has_stripped "$f" '\blist\[|\bdict\[|\bset\[|\btuple\[' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TY2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'Optional\[|Union\[' && has_outdated=true
        file_has_stripped "$f" ' \| None' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TY3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'TypeVar\(' && has_outdated=true
        file_has_stripped "$f" 'class [A-Z][a-zA-Z_]*\[' && has_modern=true
        file_has_stripped "$f" 'def [a-z_]*\[' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TY4() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has_stripped "$f" '@override' && { echo "MODERN"; return; }
    done
    echo "NONE"
}

check_TY5() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'ParamSpec\(' && has_modern=true
        if ! $has_modern && file_has_stripped "$f" '\*args:\s*Any.*\*\*kwargs:\s*Any'; then has_outdated=true; fi
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_TY6() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'TypeGuard\[' && has_outdated=true
        file_has_stripped "$f" 'TypeIs\[' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DJ1() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'django' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'from django\.contrib\.postgres\.fields import JSONField|from django\.contrib\.postgres import.*JSONField' && has_outdated=true
        file_has_stripped "$f" 'models\.JSONField|from django\.db\.models import.*JSONField' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DJ2() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'CheckConstraint' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'check\s*=' && has_outdated=true
        file_has_stripped "$f" 'condition\s*=' && has_modern=true
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_DJ3() {
    local d="$1"
    local f
    for f in "$d"/*.py; do
        [ -f "$f" ] || continue
        file_has "$f" 'django' || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'sync_to_async\(' && has_outdated=true
        file_has_stripped "$f" 'async def.*view|async def.*get\b|async def.*post\b|\.aget\(|\.afirst\(|\.acount\(' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PT1() {
    local d="$1"
    local f
    for f in "$d"/test_*.py "$d"/tests/test_*.py; do
        [ -f "$f" ] || continue
        local has_modern=false
        file_has_stripped "$f" '@pytest\.mark\.parametrize\(' && has_modern=true
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PT2() {
    local d="$1"
    local f
    for f in "$d"/test_*.py "$d"/tests/test_*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" 'pytest\.raises\(.*match=' && has_modern=true
        if ! $has_modern && file_has_stripped "$f" 'pytest\.raises\('; then has_outdated=true; fi
        if $has_outdated; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

check_PT3() {
    local d="$1"
    local f
    for f in "$d"/test_*.py "$d"/tests/test_*.py; do
        [ -f "$f" ] || continue
        local has_outdated=false has_modern=false
        file_has_stripped "$f" '\btmpdir\b' && has_outdated=true
        file_has_stripped "$f" '\btmp_path\b' && has_modern=true
        if $has_outdated && ! $has_modern; then echo "OUTDATED"; return; fi
        if $has_modern; then echo "MODERN"; return; fi
    done
    echo "NONE"
}

# --- Variant manifests ---

VARIANT_A_SCORED=(AS1 AS2 AS3 DS1 DS2 DS3 FA1 FA2 FA3 HX1 HX2 PD1 PD2 PD3 PD4 SA1 SA2 SA3 SL1 SL2 SL3 SL4 TC1 TC2 TC3 TC4 TY1 TY2 TY3 TY4 TY5 TY6)
VARIANT_A_INFO=(TC5)

VARIANT_B_SCORED=(DJ1 DJ2 DJ3)
VARIANT_B_INFO=()

VARIANT_C_SCORED=(PT1 PT2 PT3)
VARIANT_C_INFO=()

# Item labels for readable output (bash 3 compatible — no associative arrays)
item_label() {
    case "$1" in
        AS1) echo "taskgroup-over-gather" ;;
        AS2) echo "async-timeout-context" ;;
        AS3) echo "exception-groups" ;;
        DS1) echo "dataclass-modern" ;;
        DS2) echo "dict-merge-operator" ;;
        DS3) echo "match-case-patterns" ;;
        FA1) echo "fastapi-lifespan" ;;
        FA2) echo "fastapi-annotated-depends" ;;
        FA3) echo "fastapi-typed-state" ;;
        HX1) echo "httpx-async-client-reuse" ;;
        HX2) echo "httpx-streaming" ;;
        PD1) echo "pydantic-v2-config" ;;
        PD2) echo "pydantic-v2-model-api" ;;
        PD3) echo "pydantic-v2-serialization" ;;
        PD4) echo "pydantic-v2-validators" ;;
        SA1) echo "sqlalchemy-2-style" ;;
        SA2) echo "sqlalchemy-async-session" ;;
        SA3) echo "sqlalchemy-mapped-column" ;;
        SL1) echo "datetime-utc" ;;
        SL2) echo "pathlib-over-os-path" ;;
        SL3) echo "removeprefix-removesuffix" ;;
        SL4) echo "tomllib-builtin" ;;
        TC1) echo "pyproject-toml-over-setup" ;;
        TC2) echo "ruff-over-flake8" ;;
        TC3) echo "safe-subprocess" ;;
        TC4) echo "no-pickle" ;;
        TC5) echo "uv-over-pip" ;;
        TY1) echo "use-builtin-generics" ;;
        TY2) echo "union-syntax" ;;
        TY3) echo "type-parameter-syntax" ;;
        TY4) echo "override-decorator" ;;
        TY5) echo "paramspec-decorators" ;;
        TY6) echo "typeis-vs-typeguard" ;;
        DJ1) echo "django-json-field" ;;
        DJ2) echo "django-check-constraints" ;;
        DJ3) echo "django-async-views" ;;
        PT1) echo "pytest-parametrize" ;;
        PT2) echo "pytest-raises-match" ;;
        PT3) echo "pytest-tmp-path" ;;
        *) echo "unknown" ;;
    esac
}

# --- Score a session ---

score_session() {
    local session_name="$1"
    local src_dir="$RESULTS_DIR/$session_name/src"
    local scored_items=()
    local info_items=()
    local variant_name=""

    case "$VARIANT" in
        a) scored_items=("${VARIANT_A_SCORED[@]}"); info_items=("${VARIANT_A_INFO[@]}"); variant_name="A (FastAPI ecosystem)" ;;
        b) scored_items=("${VARIANT_B_SCORED[@]}"); info_items=(); variant_name="B (Django)" ;;
        c) scored_items=("${VARIANT_C_SCORED[@]}"); info_items=(); variant_name="C (pytest)" ;;
    esac

    # For variant B, try myapp/ subdirectory as well
    if [ "$VARIANT" = "b" ] && [ ! -d "$src_dir" ]; then
        src_dir="$RESULTS_DIR/$session_name/myapp"
        [ ! -d "$src_dir" ] && src_dir="$RESULTS_DIR/$session_name"
    fi
    # For variant C, test files may be at top level
    if [ "$VARIANT" = "c" ]; then
        src_dir="$RESULTS_DIR/$session_name"
    fi

    if [ ! -d "$src_dir" ] && [ ! -d "$RESULTS_DIR/$session_name" ]; then
        echo "  [ERROR] Directory not found: $src_dir"
        return
    fi

    local modern=0
    local outdated=0
    local none_count=0
    local denominator=${#scored_items[@]}
    local details=""
    local current_category=""

    for item in "${scored_items[@]}"; do
        local category="${item%%[0-9]*}"
        if [ "$category" != "$current_category" ]; then
            current_category="$category"
            details+="\n"
        fi

        local result
        result=$(check_${item} "$src_dir")
        local label
        label=$(item_label "$item")

        case "$result" in
            MODERN)
                modern=$((modern + 1))
                details+="  ✓ $item: MODERN ($label)\n"
                ;;
            OUTDATED)
                outdated=$((outdated + 1))
                details+="  ✗ $item: OUTDATED ($label)\n"
                ;;
            NONE)
                none_count=$((none_count + 1))
                details+="  · $item: NONE ($label)\n"
                ;;
        esac
    done

    local info_details=""
    for item in ${info_items[@]+"${info_items[@]}"}; do
        local result
        result=$(check_${item} "$src_dir")
        local label
        label=$(item_label "$item")
        info_details+="  ℹ $item: $result ($label) [informational]\n"
    done

    local score
    if [ "$denominator" -gt 0 ]; then
        score=$(echo "scale=1; $modern * 100 / $denominator" | bc)
    else
        score="0"
    fi

    echo "  Score: $modern / $denominator ($score%)"
    echo "  Modern: $modern  Outdated: $outdated  Not detected: $none_count"
    echo ""
    echo -e "$details"
    if [ -n "$info_details" ]; then
        echo -e "$info_details"
    fi
}

# --- Token analysis ---

token_analysis() {
    local json_a="$RESULTS_DIR/session-a.json"
    local json_b="$RESULTS_DIR/session-b.json"

    if [ ! -f "$json_a" ] || [ ! -f "$json_b" ]; then
        echo "  [SKIP] Session JSON files not found."
        return
    fi

    echo "  --- Token analysis ---"
    python3 -c "
import json
with open('$json_a') as f:
    a = json.load(f)['usage']
with open('$json_b') as f:
    b = json.load(f)['usage']

def iter0_total(u):
    iters = u.get('iterations', [])
    if not iters:
        return u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('input_tokens', 0)
    i = iters[0]
    return i.get('cache_creation_input_tokens', 0) + i.get('cache_read_input_tokens', 0) + i.get('input_tokens', 0)

ta = iter0_total(a)
tb = iter0_total(b)
diff = tb - ta
print(f'  Control iter0 total:   {ta:,} tokens')
print(f'  Treatment iter0 total: {tb:,} tokens')
print(f'  Difference (B - A):    {diff:+,} tokens')
" 2>/dev/null || echo "  [SKIP] Token analysis failed"
    echo ""
}

# --- Main ---

case "$VARIANT" in
    a) variant_display="A (FastAPI ecosystem, 32 scored + 1 info)" ;;
    b) variant_display="B (Django, 3 scored)" ;;
    c) variant_display="C (pytest, 3 scored)" ;;
    *) echo "ERROR: Unknown variant '$VARIANT'. Use a, b, or c." >&2; exit 1 ;;
esac

echo "=== V4 Benchmark Scoring: Variant $variant_display, Run $RUN_ID ==="
echo ""

echo "--- Control (no guidance) ---"
score_session "control"

echo "--- Treatment (with guidance) ---"
score_session "treatment"

token_analysis
