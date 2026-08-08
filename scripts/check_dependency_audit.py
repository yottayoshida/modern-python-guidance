#!/usr/bin/env python3
"""Decide what a `uv audit` run actually established, and report it.

Split out of the workflow YAML on purpose. The interesting failure here is not
"a vulnerability exists" — that path is easy — but "the audit did not really
look at this project and said nothing anyway". That judgement needs fixtures
and tests, which an inline shell step cannot have.

Reads the audit JSON on stdin, takes the audit command's exit status as an
argument, and exits:

* ``0`` — the audit ran, covered a plausible dependency set, and found nothing.
* ``1`` — the audit ran and found vulnerabilities. A rendered report is written
  to stdout for the caller to file as an issue.
* ``2`` — the audit did not establish anything: the command was missing, the
  output was not the shape this script understands, or it covered implausibly
  few packages. This is a failure, never "no vulnerabilities".

That last case is the reason this file exists. While designing the audit, a
bare ``pip-audit`` invocation reported "No known vulnerabilities found" against
its own 29 dependencies rather than this project's — a clean verdict over the
wrong corpus. The count was not zero, so counting alone would not have caught
it. `uv audit` resolves the project in the working directory, so that exact
mix-up cannot recur, but the lesson generalizes: a verdict is only worth what
its corpus is, so the corpus is checked before the verdict is believed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

EXIT_CLEAN = 0
EXIT_VULNERABLE = 1
EXIT_INCONCLUSIVE = 2

# `uv audit` exit codes, measured against uv 0.11.23 (2026-08-08): 0 with no
# findings, 1 with findings, 127 when the subcommand does not exist. Anything
# else is a failure we should not interpret.
AUDIT_EXIT_CLEAN = 0
AUDIT_EXIT_FOUND = 1

# The audit JSON reports how many packages it covered but not which ones, so a
# lower bound is the strongest available check on the corpus. Measured: 10
# packages for this project (1 runtime + 3 dev + their transitives). Half of
# that catches a collapsed resolution — dev extras dropped, or an empty
# project — while staying clear of ordinary dependency churn.
MIN_AUDITED_PACKAGES = 5


class InconclusiveAudit(Exception):
    """The audit did not establish anything about this project."""


def parse_audit(raw: str, *, audit_exit: int) -> dict[str, Any]:
    """Validate the audit output and return its parsed form.

    Raises InconclusiveAudit whenever the result cannot be trusted, rather than
    letting an unrecognized shape degrade into an implicit "nothing found".
    """
    if audit_exit not in (AUDIT_EXIT_CLEAN, AUDIT_EXIT_FOUND):
        raise InconclusiveAudit(
            f"`uv audit` exited {audit_exit}; expected {AUDIT_EXIT_CLEAN} (clean) or "
            f"{AUDIT_EXIT_FOUND} (findings). 127 usually means the subcommand is missing "
            "from this uv build."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InconclusiveAudit(f"audit output is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise InconclusiveAudit("audit output is not a JSON object")

    # Read required keys without defaults. `.get(key, [])` would turn a schema
    # change into a silent "no vulnerabilities", which is the failure mode this
    # whole script exists to prevent — `uv audit` is a preview command and says
    # its output may change without warning.
    for key in ("summary", "vulnerabilities"):
        if key not in data:
            raise InconclusiveAudit(
                f"audit output has no '{key}' key; the schema changed and this check "
                "can no longer read it"
            )
    summary, vulnerabilities = data["summary"], data["vulnerabilities"]
    if not isinstance(summary, dict):
        raise InconclusiveAudit("'summary' is not a JSON object")
    if not isinstance(vulnerabilities, list):
        raise InconclusiveAudit("'vulnerabilities' is not a JSON array")
    for key in ("audited_packages", "vulnerabilities"):
        if key not in summary:
            raise InconclusiveAudit(f"audit summary has no '{key}' key; the schema changed")

    audited = summary["audited_packages"]
    if not isinstance(audited, int) or isinstance(audited, bool):
        raise InconclusiveAudit(f"'audited_packages' is not an integer: {audited!r}")
    if audited < MIN_AUDITED_PACKAGES:
        raise InconclusiveAudit(
            f"audit covered only {audited} package(s), below the {MIN_AUDITED_PACKAGES} "
            "expected for this project. A clean result over a corpus this small says "
            "nothing; check that the audit ran in the project root with dev extras."
        )

    reported = summary["vulnerabilities"]
    if reported != len(vulnerabilities):
        raise InconclusiveAudit(
            f"summary claims {reported} vulnerabilities but the array holds "
            f"{len(vulnerabilities)}; the two disagree, so neither can be trusted"
        )

    # Each entry must carry an identifier, because that is what keys the issue.
    # Skipping malformed entries instead would report "findings" while naming
    # none of them — the same "trust a verdict you cannot account for" failure
    # this script exists to refuse.
    for i, v in enumerate(vulnerabilities):
        if not isinstance(v, dict):
            raise InconclusiveAudit(f"vulnerability {i} is not a JSON object: {v!r}")
        if not isinstance(v.get("id"), str) or not v["id"]:
            raise InconclusiveAudit(f"vulnerability {i} has no usable 'id': {v.get('id')!r}")

    # `adverse_statuses` — yanked releases and similar — is out of scope: it is
    # not a vulnerability feed, and acting on it needs a different judgement.
    # Its count is still checked for internal consistency, so a schema change
    # that repurposes the field shows up here rather than passing unnoticed.
    adverse = data.get("adverse_statuses")
    adverse_reported = summary.get("adverse_statuses")
    countable = isinstance(adverse, list) and isinstance(adverse_reported, int)
    if countable and adverse_reported != len(adverse):
        raise InconclusiveAudit(
            f"summary claims {adverse_reported} adverse statuses but the array holds "
            f"{len(adverse)}; the output is not internally consistent"
        )

    return data


def advisory_ids(data: dict[str, Any]) -> list[str]:
    """Advisory identifiers, sorted and de-duplicated.

    Every entry is known to carry one — `parse_audit` refuses output where any
    does not, rather than quietly dropping it here.
    """
    return sorted({v["id"] for v in data["vulnerabilities"]})


def advisory_key(ids: list[str]) -> str:
    """A short, stable identity for a set of advisories.

    The issue title cannot simply list them: a real run measured 46 advisories,
    which spells a 942-character title against GitHub's 256-character limit —
    the tracking issue would fail to be created at exactly the moment it
    mattered. A digest of the sorted set keys the same identity in constant
    space, and the full list lives in the body where length is not a problem.
    """
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:12]


def render_report(data: dict[str, Any]) -> str:
    ids = advisory_ids(data)
    lines = [
        "The weekly dependency audit found known advisories against this "
        "project's resolved dependencies.",
        "",
        f"Packages audited: {data['summary']['audited_packages']}",
        f"Advisory set: `{advisory_key(ids)}` ({len(ids)} advisories)",
        "",
        "<!-- The title carries a digest of the advisory set rather than the "
        "list itself; a large set would otherwise exceed GitHub's title "
        "length limit. The full list follows. -->",
        "",
        *(f"- {i}" for i in ids),
        "",
    ]
    for v in data["vulnerabilities"]:
        if not isinstance(v, dict):
            continue
        dep = v.get("dependency") or {}
        name = dep.get("name", "?") if isinstance(dep, dict) else "?"
        version = dep.get("version", "?") if isinstance(dep, dict) else "?"
        fixes = v.get("fix_versions") or []
        fixed = ", ".join(str(f) for f in fixes) if isinstance(fixes, list) and fixes else "none"
        lines += [
            f"### {v.get('id', '?')} — {name} {version}",
            "",
            f"{v.get('summary', '(no summary)')}",
            "",
            f"- Fixed in: {fixed}",
            f"- Advisory: {v.get('link', '(no link)')}",
            "",
        ]
    lines += [
        "---",
        "",
        "Filed by `.github/workflows/audit-dependencies.yml`. These are published "
        "advisories against third-party packages, tracked here in the open; report "
        "suspected vulnerabilities *in mpg itself* privately as SECURITY.md describes.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-exit",
        type=int,
        required=True,
        help="exit status of the `uv audit` invocation whose output is on stdin",
    )
    parser.add_argument(
        "--issue-title",
        action="store_true",
        help="print the tracking issue's title, which keys duplicate detection",
    )
    args = parser.parse_args(argv)

    try:
        data = parse_audit(sys.stdin.read(), audit_exit=args.audit_exit)
    except InconclusiveAudit as e:
        print(f"Dependency audit inconclusive: {e}", file=sys.stderr)
        return EXIT_INCONCLUSIVE

    if not data["vulnerabilities"]:
        print(f"No known vulnerabilities in {data['summary']['audited_packages']} packages.")
        return EXIT_CLEAN

    if args.issue_title:
        ids = advisory_ids(data)
        print(f"Dependency advisories: {len(ids)} ({advisory_key(ids)})")
    else:
        print(render_report(data))
    return EXIT_VULNERABLE


if __name__ == "__main__":
    raise SystemExit(main())
