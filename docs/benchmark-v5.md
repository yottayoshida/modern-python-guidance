# Benchmark V5: mpg lifts modern-Python adoption by up to 19pp on vague prompts

Models: Claude Opus 4.6 / 4.8 / Fable 5 | Updated: 2026-06-10 | Scorer: AST-based (`bench/score_v5.py`)

## Key finding

Scores below are "strict modern rate": among the Python patterns the model used, what percentage followed the modern idiom? (Formula: `MODERN / (MODERN + OUTDATED)`, excluding items where neither pattern appeared.)

| Prompt style | N | Control | With mpg | Delta |
|-------------|---|---------|----------|-------|
| **Terse** (2 sentences) | 3 | 79% | 98% | **+19pp** |
| **Normal** (file specs) | 3 | 93% | 100% | **+7pp** |

mpg guidance has the biggest impact when prompts are vague. Opus 4.8 writes modern Python with detailed instructions, but falls back to outdated patterns with minimal prompts. mpg substantially reduces that gap.

## What this means

With detailed prompts (file structure, function signatures), Opus 4.8 already writes 93% modern code. Guidance adds only +7pp — the model is already good enough.

With terse prompts ("build a FastAPI web crawler with SQLAlchemy and httpx"), the model drops to 79% modern. It falls back to `asyncio.gather` instead of `TaskGroup`, skips `TypeIs`, omits `ParamSpec`. mpg guidance pushes it back to 98%.

In our experience, real-world prompts tend to be closer to terse than to normal — most developers don't specify function signatures or library patterns. mpg fills the gap between what the model can do (with guidance) and what it does by default (without).

## How the benchmark works

Each run sends a prompt to Claude Code (`claude -p`) twice:
- **Control**: no guidance
- **Treatment**: mpg SKILL.md loaded as a rules file

Generated code is parsed by a Python AST scorer that checks 32 pattern items (Variant A: FastAPI + async ecosystem). Each item is classified as MODERN, OUTDATED, VALID_ALT, or NONE.

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

## Model comparison (4.6 vs 4.8 vs Fable 5)

| Model | Prompt | Control | Treatment | Delta |
|-------|--------|---------|-----------|-------|
| Opus 4.6 | Normal (N=10) | 90.0% | 95.0% | +5.0pp |
| Opus 4.6 | Terse (N=3) | 86.0% | 94.6% | +8.6pp |
| Opus 4.8 | Normal (N=3) | 93.3% | 100.0% | +6.7pp |
| Opus 4.8 | Terse (N=3) | 78.9% | 98.3% | +19.4pp |
| **Fable 5** | **Terse (N=3)** | **87.0%** | **94.9%*** | **+7.9pp*** |

\* All treatment OUTDATED hits in the Fable 5 runs were SL3 scorer false positives (legitimate `rstrip("\n")` / `rstrip("/")` char-set strips flagged as outdated). The scorer was fixed in [#129](https://github.com/yottayoshida/modern-python-guidance/issues/129); the raw figures above come from the pre-fix scorer, and the corrected figures (all 3 treatment runs 100%, delta +13.0pp) match what the post-fix scorer reports.

Opus 4.8 with detailed instructions is better than 4.6 (Control 93.3% vs 90.0%). But with terse instructions, 4.8 is worse (78.9% vs 86.0%). The model improved at following detailed specs but became more reliant on explicit instruction for pattern choices.

mpg guidance on 4.8 Terse (98%) outperforms both models without guidance.

### Fable 5 findings (Terse, N=3, 2026-06-10)

Fable 5 reverses the 4.8 terse regression: its no-guidance baseline (87.0%) beats both Opus 4.8 (78.9%) and Opus 4.6 (86.0%). The headroom for guidance shrinks accordingly, but guidance still closes the gap to 100% (corrected for #129).

Control failures concentrate on a small stubborn set rather than spreading across items:

| Item | Pattern | Control failures | Treatment |
|------|---------|------------------|-----------|
| AS1 | TaskGroup over gather | 3/3 (systematic) | fixed 3/3 |
| FA2 | Annotated Depends | 2/3 | fixed |
| DS1 | Frozen dataclass with slots | 1/3 | fixed |
| FA3 | FastAPI typed state | 1/3 | fixed |

`asyncio.gather` over `TaskGroup` (AS1) remains the one fully systematic habit, carried over from both Opus generations. On Fable 5 the value of mpg shifts from broad uplift to targeted correction of these few stubborn patterns.

Run variance is low: control scored 88.9% / 88.9% / 83.3%, treatment 95.0% / 95.0% / 94.7% (raw).

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
