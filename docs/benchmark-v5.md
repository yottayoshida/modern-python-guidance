# Benchmark V5: historical directional content-efficacy evidence

Models: Claude Opus 4.6 / 4.8 / Fable 5 | Updated: 2026-06-10 | Scorer: AST-based (`bench/score_v5.py`)

> **Promotion status:** The cells below are historical and `historical-unverified` in
> [`bench/claims/v5.json`](../bench/claims/v5.json). The original raw run directories
> and immutable scorer commit were not recorded in this repository, so these numbers
> are retained for audit history but are not promoted as product-level effectiveness
> claims. The default `mpg setup` end-to-end effectiveness is not yet measured.

## Key finding

The source-of-truth table below is generated from the claim manifest. It records
directional content-efficacy evidence for one workload and one treatment shape; it
does not measure the effectiveness of every way mpg can deliver guidance.

<!-- mpg-benchmark-source:start -->
| Claim ID | Status | Model | Prompt | N/condition | Workload | Treatment delivery | Prompt path | Scorer path | Control | With mpg | Delta |
|---|---|---|---|---:|---|---|---|---|---:|---:|---:|
| v5-fable-5-terse-a | historical-unverified | Claude Fable 5 | terse, two sentences | 3 | Variant A FastAPI web application | complete SKILL.md body copied into a Rules file | bench/prompts/v5-a-terse.txt | bench/score_v5.py | 87.0% | 94.9% | 7.9pp |
| v5-opus-4-6-normal-a | historical-unverified | Claude Opus 4.6 | normal, file specifications | 10 | Variant A FastAPI web application | complete SKILL.md body copied into a Rules file | bench/prompts/v5-a-normal.txt | bench/score_v5.py | 90.0% | 95.0% | 5.0pp |
| v5-opus-4-6-terse-a | historical-unverified | Claude Opus 4.6 | terse, two sentences | 3 | Variant A FastAPI web application | complete SKILL.md body copied into a Rules file | bench/prompts/v5-a-terse.txt | bench/score_v5.py | 86.0% | 94.6% | 8.6pp |
| v5-opus-4-8-normal-a | historical-unverified | Claude Opus 4.8 | normal, file specifications | 3 | Variant A FastAPI web application | complete SKILL.md body copied into a Rules file | bench/prompts/v5-a-normal.txt | bench/score_v5.py | 93.3% | 100.0% | 6.7pp |
| v5-opus-4-8-terse-a | historical-unverified | Claude Opus 4.8 | terse, two sentences | 3 | Variant A FastAPI web application | complete SKILL.md body copied into a Rules file | bench/prompts/v5-a-terse.txt | bench/score_v5.py | 78.9% | 98.3% | 19.4pp |
<!-- mpg-benchmark-source:end -->

Scores are "strict modern rate": among the Python patterns the model used, what percentage followed the modern idiom? (Formula: `MODERN / (MODERN + OUTDATED)`, excluding items where neither pattern appeared.)

The generated source table above is the only retained numeric summary for the
`v5-opus-4-8-terse-a` and `v5-opus-4-8-normal-a` manifest rows. Both rows are
`historical-unverified` because their raw run directories and immutable scorer commit
were not recorded; they are not eligible for a promoted product claim.

In this historical cell, the treatment/control gap is larger for the terse prompt.
That directional observation is limited to the named model, workload, metric, and
full-content Rules treatment; it is not a claim about unspecified agents or projects.

## Historical interpretation (not a product claim)

For the archived detailed-prompt cell, see manifest row `v5-opus-4-8-normal-a` for
the recorded control/treatment values and traceability status. The cell is small and
unverified.

For the archived terse-prompt cell, see manifest row `v5-opus-4-8-terse-a` for the
recorded control/treatment values and traceability status. The metric excludes
patterns the model did not emit, so it is not a completeness score.

Do not extrapolate these cells to other models, workloads, prompt styles, or delivery
methods. Default `mpg setup` end-to-end effectiveness is not yet measured.

## How the benchmark works

Each run sends a prompt to Claude Code (`claude -p`) twice:
- **Control**: no guidance
- **Treatment**: mpg SKILL.md loaded as a rules file

Generated code is parsed by a Python AST scorer that checks 32 pattern items (Variant A: FastAPI + async ecosystem). Each item is classified as MODERN, OUTDATED, VALID_ALT, or NONE.

## Delivery and measurement scope

Content efficacy and shipped delivery effectiveness are different measurements. The
product exposes five delivery shapes, but the historical V5 cells above measure only
the first row:

| Delivery shape | What this evidence says | Measurement status |
|---|---|---|
| Full-content Rules injection | The complete `SKILL.md` body was copied into a Rules file for treatment runs. | V5 historical directional evidence; raw inputs unverified. |
| Shipped thin Rules | The packaged Rules file is a smaller delivery artifact than the full skill body. | Not measured for strict-modern-rate uplift. |
| MCP retrieval | An agent retrieves selected guides through `search_guides`/`retrieve_guides`. | Not measured for strict-modern-rate uplift in V5. |
| Skill activation | An agent activates the packaged Agent Skill according to its own session behavior. | Not measured for strict-modern-rate uplift in V5. |
| Hook/check | `mpg setup` registers the PostToolUse hook and `mpg check` scans edited files. | Not measured for strict-modern-rate uplift. |

The V6 harness is designed to exercise real `mpg setup` conditions, catalog reach, and
hook firing. Those are delivery/reach measurements, not evidence that a hook raises
the strict-modern-rate score. Default `mpg setup` end-to-end effectiveness remains
**not yet measured**; no unrun harness is treated as evidence.

### Prompt designs

**Normal**: specifies 7 files with function-level descriptions. "Write a function `crawl(urls)` that fetches URLs concurrently using httpx. Use structured concurrency for concurrent fetches." No pattern names mentioned.

**Terse**: 2 sentences. "Build a FastAPI web application with an async web crawler. Use SQLAlchemy for the database, httpx for HTTP requests, Pydantic for data validation, and TOML for configuration."

Neither prompt mentions specific pattern names (no "TaskGroup", no "field_validator").

## Per-item analysis (Normal, N=3, Opus 4.8)

### Items where guidance helps

| Item | Pattern | Control | Treatment |
|------|---------|---------|-----------|
| TY6 | TypeIs over TypeGuard | 0/3 | 3/3 |
| PD2 | model_validate/model_dump | 0/3 | 3/3 |
| TY5 | ParamSpec decorators | 0/3 | 3/3 |
| AS1 | TaskGroup over gather | 2/3 | 3/3 |
| FA2 | Annotated Depends | 2/3 | 3/3 |
| TY3 | Type parameter syntax | 2/3 | 3/3 |

### Saturated (modern without guidance)

20 of 32 items score MODERN in both conditions. The model already knows these: `list[]` over `typing.List`, `pathlib` over `os.path`, Pydantic V2 config, SQLAlchemy 2.0 `select()`, etc.

### Stubborn (guidance doesn't help)

| Item | Pattern | Notes |
|------|---------|-------|
| DS1 | Frozen dataclass with slots | Model omits `slots=True` consistently |
| PD3 | field_serializer | Prompt doesn't elicit serialization code |

## Archival model comparison (all rows historical-unverified)

The generated source table above is the canonical comparison for the five manifest
rows: `v5-opus-4-6-normal-a`, `v5-opus-4-6-terse-a`, `v5-opus-4-8-normal-a`,
`v5-opus-4-8-terse-a`, and `v5-fable-5-terse-a`. Their model, prompt, sample,
workload, delivery, prompt path, scorer path, and traceability status are all
recorded there.

The Fable 5 row retains the existing scorer caveat: legitimate character-set strips
were previously flagged by SL3, and the scorer was fixed in [#129](https://github.com/yottayoshida/modern-python-guidance/issues/129).

The archived model rows should not be used to rank models or infer behavior outside
the named workload and delivery shape.

The archived Opus 4.8 terse row has the largest recorded delta in the source table;
its unverified status and narrow workload prevent a product-wide comparison.

### Fable 5 findings (Terse, N=3, 2026-06-10)

The archived Fable 5 terse row is a separate historical cell. Its raw scorer caveat
and missing run artifacts mean it cannot establish a general model ranking or a
promoted effectiveness claim.

Control failures concentrate on a small stubborn set rather than spreading across items:

| Item | Pattern | Control failures | Treatment |
|------|---------|------------------|-----------|
| AS1 | TaskGroup over gather | 3/3 (systematic) | fixed 3/3 |
| FA2 | Annotated Depends | 2/3 | fixed |
| DS1 | Frozen dataclass with slots | 1/3 | fixed |
| FA3 | FastAPI typed state | 1/3 | fixed |

`asyncio.gather` over `TaskGroup` (AS1) remains the one fully systematic habit, carried over from both Opus generations. On Fable 5 the value of mpg shifts from broad uplift to targeted correction of these few stubborn patterns.

Run variance observations from the original notes are retained only as qualitative
context; no additional numeric cell is promoted without a manifest row and raw-input
traceability.

## Limitations

- **Three models tested**: Opus 4.6, Opus 4.8, and Fable 5 (terse only). Other models/versions may differ; Fable 5 normal-granularity runs not yet done
- **Single app type**: FastAPI web app only. CLI, data pipeline, library not covered
- **N=3**: small sample. Directional signal is clear but not statistically rigorous
- **Normal prompt is generous**: specifies file structure and function signatures, more detailed than typical usage
- **Strict metric excludes NONE**: a high strict score means "among patterns the model used, most are modern" — not "the model used all patterns"

## Reproducing

### Cost and credit safety

Treat automated V5 benchmark runs as potentially credit-consuming. This policy was
updated on 2026-06-21 after `claude -p` benchmark sessions were reported to consume
credits in some Claude setups. `--max-budget-usd` is a per-session guard for the CLI
run; it is not a promise that a subscription plan makes the run free.

Always start with `--dry-run`, check the total session count, and only run the
automated benchmark if you are willing to spend credits for every listed session.
`bench/run-v5.sh` requires `--allow-credit-use` for non-dry-run execution.

### Low-cost manual path

Use this path for documentation checks or small spot checks where a full automated
benchmark would be too expensive:

```bash
# Prerequisites: Claude CLI/account you are willing to benchmark with, Python 3.12+

# Inspect the exact prompts and session count; this does not call claude -p
./bench/run-v5.sh test both --variant a --granularity normal -N 3 --dry-run
```

Then manually run the prompt files in the Claude session type you intend to measure:

- Control: run the prompt without mpg guidance.
- Treatment: create `.claude/rules/modern-python.md` from `skills/modern-python-guidance/SKILL.md`, then run the same prompt.
- Save generated files under a scorer-compatible directory such as
  `results/run-manual-1-v5an/<control|treatment>/`, then score `manual-1-v5an`.

Score any collected run with:

```bash
python3 bench/score_v5.py myrun-1-v5an --variant a
python3 bench/score_v5.py myrun-1-v5an --variant a --format json
```

This manual path is lower cost because you can run one prompt/session at a time and
stop as soon as you have the evidence needed for the check.

### Automated path

Only use the automated path after reviewing the dry-run output:

```bash
# Run (6 sessions per granularity, ~20 min each)
MODEL=claude-opus-4-8 ./bench/run-v5.sh myrun both --variant a --granularity normal -N 3 --allow-credit-use
MODEL=claude-opus-4-8 ./bench/run-v5.sh myrun-t both --variant a --granularity terse -N 3 --allow-credit-use

# Fable 5: June 2026 runs were observed around $1.6-3.8 estimated cost per session.
# Set a higher budget guard only after reviewing the current dry-run session count.
MODEL=claude-fable-5 ./bench/run-v5.sh myrun-f both --variant a --granularity terse -N 3 --budget 10.00 --allow-credit-use
```

The older V1/V2 procedure in `docs/benchmark-procedure.md` is historical. Issue
[#124](https://github.com/yottayoshida/modern-python-guidance/issues/124) tracks
consolidating the benchmark docs so V5 is the single primary reproduction path.

## Appendix: V5 scorer changes from V4

- **AST-based detection**: structurally correct, immune to docstring/comment false positives (fixed 3 V4 bugs)
- **VALID_ALT classification**: SA2 (sync SQLAlchemy 2.0), TY6 (TypeGuard), AS3 (per-task except)
- **Dual reporting**: strict (MODERN only) and inclusive (MODERN + VALID_ALT)
- **.venv exclusion**: terse prompts may trigger `uv sync`; third-party code is excluded from scoring
