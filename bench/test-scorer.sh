#!/usr/bin/env bash
set -euo pipefail

# TDD test for score-v4.sh using fixture files
# Validates scorer accuracy without LLM dependency

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCORER="$REPO_DIR/bench/score-v4.sh"
FIXTURES="$REPO_DIR/bench/fixtures"
PASS=0
FAIL=0
ERRORS=""

run_fixture_test() {
    local variant="$1" fixture="$2" expected_modern="$3" expected_denom="$4" label="$5"
    local fixture_dir="$FIXTURES/$fixture"
    local run_id="fixture-$(echo "$fixture" | tr '/' '-')"
    local results_dir="$REPO_DIR/results/run-${run_id}"

    # Clean up any previous test run (use /bin/rm to bypass PATH shims)
    /bin/rm -rf "$results_dir"
    mkdir -p "$results_dir/control" "$results_dir/treatment"

    # Copy fixture to both control and treatment
    if [ -d "$fixture_dir/src" ]; then
        cp -r "$fixture_dir/src" "$results_dir/control/src"
        cp -r "$fixture_dir/src" "$results_dir/treatment/src"
    fi
    if [ -d "$fixture_dir/myapp" ]; then
        cp -r "$fixture_dir/myapp" "$results_dir/control/myapp"
        cp -r "$fixture_dir/myapp" "$results_dir/treatment/myapp"
    fi
    if [ -d "$fixture_dir/tests" ]; then
        cp -r "$fixture_dir/tests" "$results_dir/control/tests"
        cp -r "$fixture_dir/tests" "$results_dir/treatment/tests"
    fi
    if [ -f "$fixture_dir/pyproject.toml" ]; then
        cp "$fixture_dir/pyproject.toml" "$results_dir/control/pyproject.toml"
        cp "$fixture_dir/pyproject.toml" "$results_dir/treatment/pyproject.toml"
    fi
    if [ -f "$fixture_dir/setup.py" ]; then
        cp "$fixture_dir/setup.py" "$results_dir/control/setup.py"
        cp "$fixture_dir/setup.py" "$results_dir/treatment/setup.py"
    fi

    # Run scorer
    local output
    output=$(VARIANT="$variant" "$SCORER" "$run_id" 2>&1) || true

    # Extract control score
    local actual_modern
    actual_modern=$(echo "$output" | awk '/--- Control/,/--- Treatment/{if(/Score:/){sub(/.*Score: /,"");sub(/ \/.*/,"");print;exit}}')

    # Clean up test results
    /bin/rm -rf "$results_dir"

    if [ "$actual_modern" = "$expected_modern" ]; then
        PASS=$((PASS + 1))
        echo "  [PASS] $label: $actual_modern/$expected_denom"
    else
        FAIL=$((FAIL + 1))
        local msg="  [FAIL] $label: expected $expected_modern/$expected_denom, got ${actual_modern:-???}"
        ERRORS+="$msg\n"
        echo "$msg"
        # Show details for debugging
        echo "$output" | grep -E '✓|✗|·' | head -20
    fi
}

echo "=== Scorer V4 TDD Tests ==="
echo ""

echo "--- Variant A (FastAPI ecosystem) ---"
run_fixture_test "a" "variant-a-modern" "32" "32" "A-modern: all modern patterns"
run_fixture_test "a" "variant-a-outdated" "0" "32" "A-outdated: all outdated patterns"

echo ""
echo "--- Variant B (Django) ---"
run_fixture_test "b" "variant-b-modern" "3" "3" "B-modern: all modern patterns"
run_fixture_test "b" "variant-b-outdated" "0" "3" "B-outdated: all outdated patterns"

echo ""
echo "--- Variant C (pytest) ---"
run_fixture_test "c" "variant-c-modern" "3" "3" "C-modern: all modern patterns"
run_fixture_test "c" "variant-c-outdated" "0" "3" "C-outdated: all outdated patterns"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Failures:"
    echo -e "$ERRORS"
    exit 1
fi
