"""Tests for scripts/check_dependency_audit.py (#165).

The point of these is not that a vulnerability is reported — it is that a
*clean* verdict is only accepted when the audit demonstrably looked at
something. Every "inconclusive" case below returns exit 2, never 0.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_dependency_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_dependency_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load_script()


def clean_output(audited: int = 10) -> dict[str, Any]:
    """Shape measured from `uv audit --output-format json` on this project."""
    return {
        "schema": {"version": "preview"},
        "summary": {"audited_packages": audited, "vulnerabilities": 0, "adverse_statuses": 0},
        "vulnerabilities": [],
        "adverse_statuses": [],
    }


def vulnerable_output() -> dict[str, Any]:
    """Shape measured from a PEP 723 script pinning jinja2==2.11.0."""
    return {
        "schema": {"version": "preview"},
        "summary": {"audited_packages": 10, "vulnerabilities": 2, "adverse_statuses": 0},
        "vulnerabilities": [
            {
                "dependency": {"name": "jinja2", "version": "2.11.0"},
                "id": "GHSA-cpwx-vrp4-4pq7",
                "display_id": "GHSA-cpwx-vrp4-4pq7",
                "aliases": ["CVE-2025-27516"],
                "summary": "Jinja2 vulnerable to sandbox breakout through attr filter",
                "description": "An oversight in ...",
                "fix_versions": ["3.1.6"],
                "link": "https://nvd.nist.gov/vuln/detail/CVE-2025-27516",
            },
            {
                "dependency": {"name": "jinja2", "version": "2.11.0"},
                "id": "GHSA-g3rq-g295-4j3m",
                "display_id": "GHSA-g3rq-g295-4j3m",
                "aliases": ["CVE-2020-28493"],
                "summary": "Regular Expression Denial of Service (ReDoS) in Jinja2",
                "description": "...",
                "fix_versions": ["2.11.3"],
                "link": "https://nvd.nist.gov/vuln/detail/CVE-2020-28493",
            },
        ],
        "adverse_statuses": [],
    }


def run(
    payload: object,
    *,
    audit_exit: int,
    argv: list[str] | None = None,
) -> tuple[int, str, str]:
    """Drive the script's main() over `payload`, returning (exit, stdout, stderr)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = io.StringIO(raw), io.StringIO(), io.StringIO()
    try:
        code = audit.main([f"--audit-exit={audit_exit}", *(argv or [])])
        return code, sys.stdout.getvalue(), sys.stderr.getvalue()
    finally:
        sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr


class TestConclusiveRuns:
    def test_clean_audit_passes(self):
        code, out, _ = run(clean_output(), audit_exit=0)
        assert code == audit.EXIT_CLEAN
        assert "10 packages" in out

    def test_findings_are_reported(self):
        code, out, _ = run(vulnerable_output(), audit_exit=1)
        assert code == audit.EXIT_VULNERABLE
        assert "GHSA-cpwx-vrp4-4pq7" in out
        assert "jinja2 2.11.0" in out
        assert "3.1.6" in out

    def test_advisory_ids_are_sorted_and_deduplicated(self):
        payload = vulnerable_output()
        payload["vulnerabilities"].append(dict(payload["vulnerabilities"][0]))
        payload["summary"]["vulnerabilities"] = 3
        data = audit.parse_audit(json.dumps(payload), audit_exit=1)
        assert audit.advisory_ids(data) == ["GHSA-cpwx-vrp4-4pq7", "GHSA-g3rq-g295-4j3m"]

    def test_issue_title_stays_short_for_a_large_advisory_set(self):
        """A measured run found 46 advisories. Listing them would spell a
        942-character title against GitHub's 256-character limit — the tracking
        issue would fail to be created exactly when it was needed."""
        payload = clean_output()
        payload["vulnerabilities"] = [
            {
                "id": f"GHSA-{i:04d}-aaaa-bbbb",
                "dependency": {"name": "pkg", "version": "1.0"},
                "summary": "s",
                "fix_versions": [],
                "link": "https://example.invalid",
            }
            for i in range(46)
        ]
        payload["summary"]["vulnerabilities"] = 46
        code, out, _ = run(payload, audit_exit=1, argv=["--issue-title"])
        assert code == audit.EXIT_VULNERABLE
        title = out.strip()
        assert len(title) <= 256, len(title)
        assert "46" in title

    def test_issue_title_changes_with_the_advisory_set(self):
        """The title is the duplicate-detection key, so a different set of
        advisories must not collide with an existing issue."""
        first = vulnerable_output()
        second = vulnerable_output()
        second["vulnerabilities"] = second["vulnerabilities"][:1]
        second["summary"]["vulnerabilities"] = 1

        _, title_a, _ = run(first, audit_exit=1, argv=["--issue-title"])
        _, title_b, _ = run(second, audit_exit=1, argv=["--issue-title"])
        assert title_a != title_b

    def test_report_lists_every_advisory_id(self):
        """What the title drops for length has to survive in the body."""
        _, out, _ = run(vulnerable_output(), audit_exit=1)
        assert "GHSA-cpwx-vrp4-4pq7" in out
        assert "GHSA-g3rq-g295-4j3m" in out

    def test_non_ghsa_advisory_ids_are_carried_through(self):
        """`uv audit` mixes identifier schemes — a live run returned 23 GHSA
        and 23 PYSEC ids. Anything keying on the GHSA prefix would silently
        drop half the findings."""
        payload = vulnerable_output()
        payload["vulnerabilities"].append(
            {
                "dependency": {"name": "requests", "version": "2.19.0"},
                "id": "PYSEC-2018-28",
                "summary": "requests before 2.20.0 sends Authorization on redirect",
                "fix_versions": ["2.20.0"],
                "link": "https://example.invalid",
            }
        )
        payload["summary"]["vulnerabilities"] = 3
        _, out, _ = run(payload, audit_exit=1)
        assert "PYSEC-2018-28" in out
        assert out.count("PYSEC-2018-28") >= 2, "expected it in both the list and the detail"

    def test_report_points_at_the_private_channel_for_mpgs_own_issues(self):
        """SECURITY.md forbids public issues for suspected vulnerabilities *in
        mpg*. This report is public by design, so it has to draw that line."""
        _, out, _ = run(vulnerable_output(), audit_exit=1)
        assert "SECURITY.md" in out
        assert "privately" in out


class TestInconclusiveRuns:
    """Each of these must be a failure, never a clean verdict."""

    def test_a_clean_verdict_over_a_tiny_corpus_is_rejected(self):
        """The defect this whole script exists for.

        While designing this audit, a bare `pip-audit` reported "No known
        vulnerabilities found" — against its own dependencies, not this
        project's. A verdict is only worth what its corpus is.
        """
        code, _, err = run(clean_output(audited=1), audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "below the" in err

    def test_zero_packages_is_rejected(self):
        code, _, err = run(clean_output(audited=0), audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "0 package" in err

    def test_missing_vulnerabilities_key_is_rejected(self):
        """A defensive `.get("vulnerabilities", [])` would read a schema change
        as "nothing found". `uv audit` is a preview command; its output may
        change without warning."""
        payload = clean_output()
        del payload["vulnerabilities"]
        code, _, err = run(payload, audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "schema changed" in err

    def test_missing_summary_key_is_rejected(self):
        payload = clean_output()
        del payload["summary"]
        code, _, err = run(payload, audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "schema changed" in err

    def test_missing_audited_packages_key_is_rejected(self):
        payload = clean_output()
        del payload["summary"]["audited_packages"]
        code, _, err = run(payload, audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "audited_packages" in err

    def test_summary_disagreeing_with_the_array_is_rejected(self):
        """If the two disagree, neither can be trusted — including the case
        where the summary says 0 but findings are present."""
        payload = vulnerable_output()
        payload["summary"]["vulnerabilities"] = 0
        code, _, err = run(payload, audit_exit=1)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "disagree" in err

    def test_missing_uv_audit_subcommand_is_rejected(self):
        """Measured: a uv build without the subcommand exits 127. CI does not
        pin a uv version, so this is the realistic way the audit stops working."""
        code, _, err = run("", audit_exit=127)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "127" in err

    def test_non_json_output_is_rejected(self):
        code, _, err = run("not json at all", audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "not valid JSON" in err

    def test_json_that_is_not_an_object_is_rejected(self):
        code, _, err = run([1, 2, 3], audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "not a JSON object" in err

    def test_a_vulnerability_without_an_id_is_rejected(self):
        """The id keys the tracking issue. Skipping the entry instead would
        report "findings" while naming none of them."""
        payload = vulnerable_output()
        del payload["vulnerabilities"][0]["id"]
        code, _, err = run(payload, audit_exit=1)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "no usable 'id'" in err

    def test_a_vulnerability_that_is_not_an_object_is_rejected(self):
        payload = vulnerable_output()
        payload["vulnerabilities"][0] = "GHSA-something"
        code, _, err = run(payload, audit_exit=1)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "not a JSON object" in err

    def test_adverse_statuses_disagreeing_with_its_summary_is_rejected(self):
        """Adverse statuses are out of scope as a signal, but an output that
        cannot count its own fields is not one to trust."""
        payload = clean_output()
        payload["summary"]["adverse_statuses"] = 3
        code, _, err = run(payload, audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "adverse statuses" in err

    @pytest.mark.parametrize("bogus", [True, "10", None, 10.5])
    def test_non_integer_audited_packages_is_rejected(self, bogus):
        """`True` is the interesting one: it is an int in Python, and would
        otherwise slip past a naive comparison as `1`."""
        payload = clean_output()
        payload["summary"]["audited_packages"] = bogus
        code, _, err = run(payload, audit_exit=0)
        assert code == audit.EXIT_INCONCLUSIVE
        assert "not an integer" in err


class TestMinimumIsNotVacuous:
    def test_the_measured_project_size_clears_the_minimum(self):
        """A bound set above the real corpus would fail every run; one set at
        zero would accept anything. Pin it between."""
        assert 0 < audit.MIN_AUDITED_PACKAGES <= 10
