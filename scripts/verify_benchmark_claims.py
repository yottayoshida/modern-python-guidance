#!/usr/bin/env python3
"""Validate and render the repository's benchmark-claim contract.

The verifier is deliberately local and read-only in ``--check`` mode.  It
never starts a benchmark session, invokes an LLM, or downloads an artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
KNOWN_STATUSES = {"historical-unverified", "promoted"}
GIT_VERSION_RE = re.compile(r"^git:([0-9a-f]{40})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
README_START = "<!-- mpg-benchmark-claims:start -->"
README_END = "<!-- mpg-benchmark-claims:end -->"
SOURCE_START = "<!-- mpg-benchmark-source:start -->"
SOURCE_END = "<!-- mpg-benchmark-source:end -->"
BENCHMARK_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:%|pp)(?!\w)")


class ClaimValidationError(ValueError):
    """Raised when a benchmark claim is not safe to publish."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimValidationError(f"cannot read benchmark manifest: {path}") from exc
    if not isinstance(data, dict):
        raise ClaimValidationError("benchmark manifest must be a JSON object")
    return data


def _fail(message: str) -> None:
    raise ClaimValidationError(message)


def _require(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        _fail(f"{context} is missing required field {key!r}")
    return mapping[key]


def _tracked_paths(repo_root: Path) -> set[str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "--cached"],
            cwd=repo_root,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ClaimValidationError("cannot inspect repository-tracked paths") from exc
    return {line for line in output.splitlines() if line}


def _repo_relative_path(
    value: Any, *, repo_root: Path, tracked: set[str], context: str
) -> tuple[str, Path]:
    if not isinstance(value, str) or not value:
        _fail(f"{context} path must be a non-empty relative string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail(f"{context} path must stay inside the repository: {value!r}")
    normalized = candidate.as_posix()
    resolved = (repo_root / candidate).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        _fail(f"{context} path escapes the repository: {value!r}")
    if normalized not in tracked:
        _fail(f"{context} path is not tracked: {value!r}")
    if not resolved.is_file():
        _fail(f"{context} path does not exist: {value!r}")
    return normalized, resolved


def _validate_raw_input(
    raw_input: Any, *, repo_root: Path, tracked: set[str], context: str
) -> None:
    if not isinstance(raw_input, dict):
        _fail(f"{context} must be an object")
    raw_path = _require(raw_input, "path", context)
    sha256 = _require(raw_input, "sha256", context)
    _, resolved = _repo_relative_path(
        raw_path, repo_root=repo_root, tracked=tracked, context=context
    )
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        _fail(f"{context} sha256 must be 64 lowercase hexadecimal characters")
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual != sha256:
        _fail(f"{context} sha256 mismatch for {raw_path!r}")


def _validate_scorer(
    scorer: Any,
    *,
    status: str,
    repo_root: Path,
    tracked: set[str],
    context: str,
) -> None:
    if not isinstance(scorer, dict):
        _fail(f"{context}.scorer must be an object")
    scorer_path = _require(scorer, "path", f"{context}.scorer")
    normalized, _ = _repo_relative_path(
        scorer_path,
        repo_root=repo_root,
        tracked=tracked,
        context=f"{context}.scorer",
    )
    version = _require(scorer, "version", f"{context}.scorer")
    if status == "historical-unverified":
        if version != "unrecorded" and (
            not isinstance(version, str) or not GIT_VERSION_RE.fullmatch(version)
        ):
            _fail(f"{context}.scorer version must be 'unrecorded' or an immutable git commit")
        return
    if not isinstance(version, str) or not GIT_VERSION_RE.fullmatch(version):
        _fail(f"{context}.scorer version must be git:<40-hex commit> for promoted claims")
    commit = version.removeprefix("git:")
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        listed = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", commit, "--", normalized],
            cwd=repo_root,
            text=True,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ClaimValidationError(f"{context}.scorer commit is unavailable: {version!r}") from exc
    if normalized not in listed:
        _fail(f"{context}.scorer commit does not contain {normalized!r}")


def validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    if _require(manifest, "schema_version", "manifest") != SCHEMA_VERSION:
        _fail(f"manifest schema_version must be {SCHEMA_VERSION}")
    if _require(manifest, "benchmark", "manifest") != "V5":
        _fail("manifest benchmark must be 'V5'")
    claims = _require(manifest, "claims", "manifest")
    if not isinstance(claims, list) or not claims:
        _fail("manifest claims must be a non-empty list")

    tracked = _tracked_paths(repo_root)
    ids: set[str] = set()
    for index, claim in enumerate(claims):
        context = f"claim[{index}]"
        if not isinstance(claim, dict):
            _fail(f"{context} must be an object")
        claim_id = _require(claim, "id", context)
        if not isinstance(claim_id, str) or not claim_id:
            _fail(f"{context}.id must be a non-empty string")
        if claim_id in ids:
            _fail(f"duplicate claim id: {claim_id!r}")
        ids.add(claim_id)

        status = _require(claim, "status", context)
        if status not in KNOWN_STATUSES:
            _fail(f"{context}.status is unknown: {status!r}")
        for field in (
            "model",
            "prompt_style",
            "workload",
            "treatment_delivery",
        ):
            value = _require(claim, field, context)
            if not isinstance(value, str) or not value:
                _fail(f"{context}.{field} must be a non-empty string")

        sample_size = _require(claim, "sample_size_per_condition", context)
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
            _fail(f"{context}.sample_size_per_condition must be a positive integer")

        metric = _require(claim, "metric", context)
        if not isinstance(metric, dict):
            _fail(f"{context}.metric must be an object")
        for field in ("name", "formula"):
            value = _require(metric, field, f"{context}.metric")
            if not isinstance(value, str) or not value:
                _fail(f"{context}.metric.{field} must be a non-empty string")
        excludes = _require(metric, "excludes", f"{context}.metric")
        if not isinstance(excludes, list) or not all(
            isinstance(item, str) and item for item in excludes
        ):
            _fail(f"{context}.metric.excludes must be a list of names")

        prompt_paths = _require(claim, "prompt_paths", context)
        if not isinstance(prompt_paths, list) or not prompt_paths:
            _fail(f"{context}.prompt_paths must be a non-empty list")
        for prompt_index, prompt_path in enumerate(prompt_paths):
            _repo_relative_path(
                prompt_path,
                repo_root=repo_root,
                tracked=tracked,
                context=f"{context}.prompt_paths[{prompt_index}]",
            )

        raw_inputs = _require(claim, "raw_inputs", context)
        if not isinstance(raw_inputs, list):
            _fail(f"{context}.raw_inputs must be a list")
        if status == "promoted" and not raw_inputs:
            _fail(f"{context}.raw_inputs is required for promoted claims")
        for raw_index, raw_input in enumerate(raw_inputs):
            _validate_raw_input(
                raw_input,
                repo_root=repo_root,
                tracked=tracked,
                context=f"{context}.raw_inputs[{raw_index}]",
            )
        _validate_scorer(
            _require(claim, "scorer", context),
            status=status,
            repo_root=repo_root,
            tracked=tracked,
            context=context,
        )

        percentages: dict[str, float] = {}
        for field in ("control_percent", "treatment_percent", "delta_percentage_points"):
            value = _require(claim, field, context)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                _fail(f"{context}.{field} must be numeric")
            if not math.isfinite(float(value)):
                _fail(f"{context}.{field} must be finite")
            if field != "delta_percentage_points" and not 0 <= float(value) <= 100:
                _fail(f"{context}.{field} must be between 0 and 100")
            percentages[field] = float(value)
        expected_delta = percentages["treatment_percent"] - percentages["control_percent"]
        if not math.isclose(
            expected_delta,
            percentages["delta_percentage_points"],
            abs_tol=0.051,
        ):
            _fail(f"{context}.delta_percentage_points does not equal treatment minus control")


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _format_percent(value: float | int) -> str:
    return f"{float(value):.1f}%"


def render_readme_block(manifest: dict[str, Any]) -> str:
    promoted = [claim for claim in manifest["claims"] if claim["status"] == "promoted"]
    lines = [README_START]
    if not promoted:
        lines.append(
            "Benchmark evidence status: historical V5 cells remain documented for audit, "
            "but no traceable numeric product claim is currently promoted. Default `mpg setup` "
            "end-to-end effectiveness has not yet been measured."
        )
    else:
        lines.append(
            "Promoted benchmark evidence (each row is traceable to raw inputs and a fixed scorer):"
        )
        lines.append("")
        lines.append(
            "| Model | Prompt | N/condition | Workload | Delivery | Control | With mpg | Delta |"
        )
        lines.append("|---|---|---:|---|---|---:|---:|---:|")
        for claim in sorted(promoted, key=lambda item: item["id"]):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_table(claim["model"]),
                        _escape_table(claim["prompt_style"]),
                        str(claim["sample_size_per_condition"]),
                        _escape_table(claim["workload"]),
                        _escape_table(claim["treatment_delivery"]),
                        _format_percent(claim["control_percent"]),
                        _format_percent(claim["treatment_percent"]),
                        f"{float(claim['delta_percentage_points']):.1f}pp",
                    ]
                )
                + " |"
            )
    lines.append(README_END)
    return "\n".join(lines)


def render_source_block(manifest: dict[str, Any]) -> str:
    lines = [
        SOURCE_START,
        "| Claim ID | Status | Model | Prompt | N/condition | Workload | "
        "Treatment delivery | Prompt path | Scorer path | Control | With mpg | Delta |",
        "|---|---|---|---|---:|---|---|---|---|---:|---:|---:|",
    ]
    for claim in sorted(manifest["claims"], key=lambda item: item["id"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(claim["id"]),
                    _escape_table(claim["status"]),
                    _escape_table(claim["model"]),
                    _escape_table(claim["prompt_style"]),
                    str(claim["sample_size_per_condition"]),
                    _escape_table(claim["workload"]),
                    _escape_table(claim["treatment_delivery"]),
                    _escape_table(", ".join(claim["prompt_paths"])),
                    _escape_table(claim["scorer"]["path"]),
                    _format_percent(claim["control_percent"]),
                    _format_percent(claim["treatment_percent"]),
                    f"{float(claim['delta_percentage_points']):.1f}pp",
                ]
            )
            + " |"
        )
    lines.append(SOURCE_END)
    return "\n".join(lines)


def _replace_block(text: str, start: str, end: str, rendered: str) -> str:
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != 1 or end_count != 1:
        raise ClaimValidationError(
            f"expected exactly one {start!r}/{end!r} block, found {start_count}/{end_count}"
        )
    start_index = text.index(start)
    try:
        end_index = text.index(end, start_index) + len(end)
    except ValueError as exc:
        raise ClaimValidationError(f"{end!r} marker must follow {start!r} marker") from exc
    return text[:start_index] + rendered + text[end_index:]


def generated_block_errors(manifest: dict[str, Any], readme: str, source: str) -> list[str]:
    """Return deterministic drift errors for the generated documentation blocks."""
    errors: list[str] = []
    try:
        expected_readme = _replace_block(
            readme, README_START, README_END, render_readme_block(manifest)
        )
    except ClaimValidationError as exc:
        errors.append(str(exc))
    else:
        if readme != expected_readme:
            errors.append("README benchmark claim block is stale")
        start_index = readme.index(README_START)
        end_index = readme.index(README_END, start_index) + len(README_END)
        outside_block = readme[:start_index] + readme[end_index:]
        if BENCHMARK_NUMBER_RE.search(outside_block):
            errors.append(
                "README contains an unmanaged benchmark number outside its generated block"
            )

    try:
        expected_source = _replace_block(
            source, SOURCE_START, SOURCE_END, render_source_block(manifest)
        )
    except ClaimValidationError as exc:
        errors.append(str(exc))
    else:
        if source != expected_source:
            errors.append("docs/benchmark-v5.md source table block is stale")
    return errors


def _check_or_write(repo_root: Path, *, write: bool) -> int:
    manifest_path = repo_root / "bench" / "claims" / "v5.json"
    readme_path = repo_root / "README.md"
    source_path = repo_root / "docs" / "benchmark-v5.md"
    manifest = load_manifest(manifest_path)
    validate_manifest(manifest, repo_root)
    readme = readme_path.read_text(encoding="utf-8")
    source = source_path.read_text(encoding="utf-8")
    errors = generated_block_errors(manifest, readme, source)
    if write:
        expected_readme = _replace_block(
            readme, README_START, README_END, render_readme_block(manifest)
        )
        expected_source = _replace_block(
            source, SOURCE_START, SOURCE_END, render_source_block(manifest)
        )
        if readme != expected_readme:
            readme_path.write_text(expected_readme, encoding="utf-8")
        if source != expected_source:
            source_path.write_text(expected_source, encoding="utf-8")
        return 0
    if errors:
        for error in errors:
            print(error)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if generated blocks drift")
    mode.add_argument("--write", action="store_true", help="write only the generated blocks")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this checkout)",
    )
    args = parser.parse_args(argv)
    try:
        return _check_or_write(args.repo_root.resolve(), write=args.write)
    except ClaimValidationError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
