# Benchmark V5: mpg lifts modern-Python adoption by up to 19pp on vague prompts

Model: Claude Opus 4.8 | Date: 2026-05-30 | Scorer: AST-based (`bench/score_v5.py`)

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

## Model comparison (4.6 vs 4.8)

| Model | Prompt | Control | Treatment | Delta |
|-------|--------|---------|-----------|-------|
| Opus 4.6 | Normal (N=10) | 90.0% | 95.0% | +5.0pp |
| Opus 4.6 | Terse (N=3) | 86.0% | 94.6% | +8.6pp |
| **Opus 4.8** | **Normal (N=3)** | **93.3%** | **100.0%** | **+6.7pp** |
| **Opus 4.8** | **Terse (N=3)** | **78.9%** | **98.3%** | **+19.4pp** |

Opus 4.8 with detailed instructions is better than 4.6 (Control 93.3% vs 90.0%). But with terse instructions, 4.8 is worse (78.9% vs 86.0%). The model improved at following detailed specs but became more reliant on explicit instruction for pattern choices.

mpg guidance on 4.8 Terse (98%) outperforms both models without guidance.

## Limitations

- **Two models tested**: Opus 4.6 and 4.8. Other models/versions may differ
- **Single app type**: FastAPI web app only. CLI, data pipeline, library not covered
- **N=3**: small sample. Directional signal is clear but not statistically rigorous
- **Normal prompt is generous**: specifies file structure and function signatures, more detailed than typical usage
- **Strict metric excludes NONE**: a high strict score means "among patterns the model used, most are modern" — not "the model used all patterns"

## Reproducing

```bash
# Prerequisites: Claude CLI with Max plan, Python 3.12+

# Dry run
./bench/run-v5.sh test both --variant a --granularity normal -N 3 --dry-run

# Run (6 sessions per granularity, ~20 min each)
MODEL=claude-opus-4-8 ./bench/run-v5.sh myrun both --variant a --granularity normal -N 3
MODEL=claude-opus-4-8 ./bench/run-v5.sh myrun-t both --variant a --granularity terse -N 3

# Score
python3 bench/score_v5.py myrun-1-v5an --variant a
python3 bench/score_v5.py myrun-1-v5an --variant a --format json
```

## Appendix: V5 scorer changes from V4

- **AST-based detection**: structurally correct, immune to docstring/comment false positives (fixed 3 V4 bugs)
- **VALID_ALT classification**: SA2 (sync SQLAlchemy 2.0), TY6 (TypeGuard), AS3 (per-task except)
- **Dual reporting**: strict (MODERN only) and inclusive (MODERN + VALID_ALT)
- **.venv exclusion**: terse prompts may trigger `uv sync`; third-party code is excluded from scoring
