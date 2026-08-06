"""Tests for the traceable benchmark-claim contract."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_benchmark_claims import (  # noqa: E402
    ClaimValidationError,
    generated_block_errors,
    load_manifest,
    render_readme_block,
    render_source_block,
    validate_manifest,
)

MANIFEST_PATH = REPO_ROOT / "bench" / "claims" / "v5.json"


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()


def _claim(*, status: str = "historical-unverified") -> dict:
    return {
        "id": "test-claim",
        "status": status,
        "model": "Test model",
        "prompt_style": "terse",
        "sample_size_per_condition": 3,
        "workload": "Variant A FastAPI web application",
        "metric": {
            "name": "strict modern rate",
            "formula": "MODERN / (MODERN + OUTDATED)",
            "excludes": ["NONE", "VALID_ALT"],
        },
        "treatment_delivery": "complete SKILL.md body copied into a Rules file",
        "prompt_paths": ["bench/prompts/v5-a-terse.txt"],
        "raw_inputs": [],
        "scorer": {"path": "bench/score_v5.py", "version": "unrecorded"},
        "control_percent": 78.9,
        "treatment_percent": 98.3,
        "delta_percentage_points": 19.4,
    }


def _promoted_claim() -> dict:
    claim = _claim(status="promoted")
    claim["prompt_paths"] = [
        {
            "path": "bench/prompts/v5-a-terse.txt",
            "sha256": _sha256("bench/prompts/v5-a-terse.txt"),
        }
    ]
    claim["raw_inputs"] = [
        {
            "condition": "control",
            "run_id": "fixture-run",
            "path": "tests/fixtures/benchmark-raw/control.json",
            "sha256": _sha256("tests/fixtures/benchmark-raw/control.json"),
        },
        {
            "condition": "treatment",
            "run_id": "fixture-run",
            "path": "tests/fixtures/benchmark-raw/treatment.json",
            "sha256": _sha256("tests/fixtures/benchmark-raw/treatment.json"),
        },
    ]
    return claim


def _manifest(*claims: dict) -> dict:
    return {"schema_version": 1, "benchmark": "V5", "claims": list(claims)}


def test_repository_manifest_is_valid_and_current_cells_are_not_promoted() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    validate_manifest(manifest, REPO_ROOT)

    assert manifest["claims"]
    assert {claim["status"] for claim in manifest["claims"]} == {"historical-unverified"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("control_percent", -0.1),
        ("treatment_percent", 100.1),
        ("delta_percentage_points", 2.0),
    ],
)
def test_claim_rejects_invalid_percentages_and_delta(field: str, value: float) -> None:
    claim = _claim()
    claim[field] = value

    with pytest.raises(ClaimValidationError):
        validate_manifest(_manifest(claim), REPO_ROOT)


def test_claim_requires_unique_ids_and_known_status() -> None:
    first = _claim()
    second = copy.deepcopy(first)
    second["status"] = "not-a-status"

    with pytest.raises(ClaimValidationError):
        validate_manifest(_manifest(first, second), REPO_ROOT)

    second["status"] = "historical-unverified"
    with pytest.raises(ClaimValidationError):
        validate_manifest(_manifest(first, second), REPO_ROOT)


def test_promoted_claim_requires_hashed_raw_inputs() -> None:
    claim = _promoted_claim()
    claim["raw_inputs"] = []

    with pytest.raises(ClaimValidationError, match="raw_inputs"):
        validate_manifest(_manifest(claim), REPO_ROOT)

    claim["raw_inputs"] = [
        {
            "condition": "control",
            "run_id": "fixture-run",
            "path": "bench/prompts/v5-a-terse.txt",
        }
    ]
    with pytest.raises(ClaimValidationError, match="sha256"):
        validate_manifest(_manifest(claim), REPO_ROOT)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/raw.json",
        "../outside/raw.json",
        "bench/claims/untracked-output.json",
    ],
)
def test_promoted_claim_rejects_unsafe_or_untracked_raw_paths(path: str) -> None:
    claim = _promoted_claim()
    claim["raw_inputs"] = [
        {
            "condition": "control",
            "run_id": "fixture-run",
            "path": path,
            "sha256": "0" * 64,
        }
    ]

    with pytest.raises(ClaimValidationError, match="raw_inputs"):
        validate_manifest(_manifest(claim), REPO_ROOT)


def test_promoted_claim_rejects_existing_untracked_raw_file() -> None:
    raw_path = REPO_ROOT / "bench" / "claims" / "untracked-test-output.json"
    raw_path.write_text("temporary raw output", encoding="utf-8")
    try:
        claim = _promoted_claim()
        claim["raw_inputs"] = [
            {
                "condition": "control",
                "run_id": "fixture-run",
                "path": "bench/claims/untracked-test-output.json",
                "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            }
        ]

        with pytest.raises(ClaimValidationError, match="not tracked"):
            validate_manifest(_manifest(claim), REPO_ROOT)
    finally:
        raw_path.unlink(missing_ok=True)


def test_promoted_claim_rejects_hash_mismatch() -> None:
    claim = _promoted_claim()
    claim["raw_inputs"][0]["sha256"] = "0" * 64

    with pytest.raises(ClaimValidationError, match="sha256 mismatch"):
        validate_manifest(_manifest(claim), REPO_ROOT)


def test_promoted_claim_requires_immutable_scorer_commit() -> None:
    claim = _promoted_claim()

    with pytest.raises(ClaimValidationError, match="scorer version"):
        validate_manifest(_manifest(claim), REPO_ROOT)

    claim["scorer"]["version"] = "git:" + "0" * 40
    with pytest.raises(ClaimValidationError, match="scorer commit"):
        validate_manifest(_manifest(claim), REPO_ROOT)

    claim["scorer"]["version"] = "git:" + _git_head()
    validate_manifest(_manifest(claim), REPO_ROOT)


def test_promoted_claim_rejects_prompt_hash_drift() -> None:
    claim = _promoted_claim()
    claim["prompt_paths"][0]["sha256"] = "0" * 64

    with pytest.raises(ClaimValidationError, match=r"prompt_paths.*sha256 mismatch"):
        validate_manifest(_manifest(claim), REPO_ROOT)


def test_renderer_is_deterministic_and_contains_no_unmanaged_numeric_claims() -> None:
    manifest = _manifest(_claim())

    readme = render_readme_block(manifest)
    source = render_source_block(manifest)

    assert readme == render_readme_block(json.loads(json.dumps(manifest)))
    assert "currently promoted" in readme
    assert "historical-unverified" in source
    assert "78.9%" in source
    assert "19.4pp" in source


def test_repository_blocks_match_deterministic_renderer() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    source = (REPO_ROOT / "docs" / "benchmark-v5.md").read_text(encoding="utf-8")

    expected_readme = render_readme_block(manifest)
    expected_source = render_source_block(manifest)
    assert expected_readme in readme
    assert expected_source in source
    assert generated_block_errors(manifest, readme, source) == []


def test_check_detects_manifest_percentage_drift_without_writing_files() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    source = (REPO_ROOT / "docs" / "benchmark-v5.md").read_text(encoding="utf-8")
    changed = json.loads(json.dumps(manifest))
    changed["claims"][0]["treatment_percent"] = 95.1
    changed["claims"][0]["delta_percentage_points"] = 8.1

    errors = generated_block_errors(changed, readme, source)

    assert errors == ["docs/benchmark-v5.md source table block is stale"]


def test_check_detects_unmanaged_numeric_text_inside_readme_block() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    source = (REPO_ROOT / "docs" / "benchmark-v5.md").read_text(encoding="utf-8")
    changed_readme = readme.replace(
        "historical V5 cells remain documented",
        "historical V5 cells remain documented (98% headline)",
    )

    errors = generated_block_errors(manifest, changed_readme, source)

    assert errors == ["README benchmark claim block is stale"]


def test_check_detects_unmanaged_numeric_text_outside_readme_block() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    source = (REPO_ROOT / "docs" / "benchmark-v5.md").read_text(encoding="utf-8")

    errors = generated_block_errors(manifest, readme + "\nHistorical result: 42%.\n", source)

    assert errors == ["README contains an unmanaged benchmark number outside its generated block"]


def test_readme_does_not_promote_historical_numbers() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "AI writes modern Python 98%" not in readme
    assert "98%" not in readme
    assert "79%" not in readme


def test_docs_name_all_delivery_shapes_and_unmeasured_default_setup() -> None:
    docs = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/benchmark-v5.md",
            "docs/benchmark-evaluation.md",
            "docs/design.md",
        )
    )

    for phrase in (
        "full-content Rules injection",
        "shipped thin Rules",
        "MCP retrieval",
        "Skill activation",
        "hook/check",
    ):
        assert phrase in docs
    assert "default `mpg setup`" in docs
    assert "not yet measured" in docs
