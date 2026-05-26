# Benchmark Evaluation

Issue: #8

## Hypothesis

Embedding BAD/GOOD patterns in SKILL.md (pre-generation injection) reduces outdated Python patterns in AI-generated code, particularly for patterns that Ruff cannot auto-fix.

## Evaluation checklist (17 items)

### P-01: Pydantic model with validators (6 items)

File: `src/models.py`

| # | Outdated (BAD) | Modern (GOOD) | grep pattern |
|---|----------------|---------------|-------------|
| 1 | `@validator` | `@field_validator` | `@field_validator` |
| 2 | `@root_validator` | `@model_validator` | `@model_validator` |
| 3 | `class Config:` | `model_config = ConfigDict(...)` | `model_config` |
| 4 | `orm_mode = True` | `from_attributes = True` | `from_attributes` |
| 5 | `allow_population_by_field_name` | `populate_by_name` | `populate_by_name` |
| 6 | `.dict()` | `.model_dump()` | `\.model_dump()` |

### P-02: Pydantic serialization (5 items)

File: `src/serialization.py`

| # | Outdated (BAD) | Modern (GOOD) | grep pattern |
|---|----------------|---------------|-------------|
| 1 | `.parse_obj()` | `.model_validate()` | `\.model_validate(` |
| 2 | `.parse_raw()` | `.model_validate_json()` | `\.model_validate_json(` |
| 3 | `.json()` | `.model_dump_json()` | `\.model_dump_json()` |
| 4 | `.schema()` | `.model_json_schema()` | `\.model_json_schema()` |
| 5 | `.copy()` | `.model_copy()` | `\.model_copy(` |

### P-03: FastAPI lifecycle (3 items)

File: `src/app.py`

| # | Outdated (BAD) | Modern (GOOD) | grep pattern |
|---|----------------|---------------|-------------|
| 1 | `@app.on_event("startup")` | lifespan context manager | `lifespan` |
| 2 | `@app.on_event("shutdown")` | lifespan context manager | (same as above) |
| 3 | `Depends()` without `Annotated` | `Annotated[..., Depends()]` | `Annotated\[` |

### P-04: Async HTTP (2 items)

File: `src/fetcher.py`

| # | Outdated (BAD) | Modern (GOOD) | grep pattern |
|---|----------------|---------------|-------------|
| 1 | Per-request `AsyncClient` | Shared `AsyncClient` | `AsyncClient` |
| 2 | `asyncio.gather()` | `asyncio.TaskGroup` | `TaskGroup` |

### P-05: Subprocess (1 item)

File: `src/runner.py`

| # | Outdated (BAD) | Modern (GOOD) | grep pattern |
|---|----------------|---------------|-------------|
| 2 | `subprocess.run(f"...", shell=True)` | `subprocess.run(["cmd", arg])` | `shell=True` (inverse) |

**P-05-1 excluded**: The prompt asks for `pyproject.toml` explicitly. Not a valid test.

## Scoring

| Metric | Formula |
|--------|---------|
| Modern patterns | Count of GOOD patterns detected |
| Outdated patterns | Count of BAD patterns detected |
| Score | `modern / 17 * 100` (%) |
| Improvement | Treatment score - Control score (pp) |

All 17 patterns are Ruff-uncoverable, so any improvement is attributable to SKILL.md.

## Interpretation

| Improvement | Meaning | Action |
|-------------|---------|--------|
| 0-10pp | Marginal | Reconsider product positioning |
| 10-30pp | Moderate | Strengthen SKILL.md, add more patterns |
| 30pp+ | Strong | Double down on SKILL.md approach |

## Results

### Run 0 (2026-05-26) — INVALID

Evaluation checklists leaked into prompts. Both sessions scored 18/18. Discarded.

### Run 1 (2026-05-26)

| Session | Modern | Outdated | Total | Score |
|---------|--------|----------|-------|-------|
| Control (A) | 16 | 1 | 17 | 94.1% |
| Treatment (B) | 15 | 2 | 17 | 88.2% |
| **Improvement** | | | | **-5.9pp** |

Outdated in Control: P-04-2 (asyncio.gather)
Outdated in Treatment: P-03-3 (Depends without Annotated), P-04-2 (asyncio.gather)

Skill load verification:
- Physical: PASS (Control=ABSENT, Treatment=PRESENT)
- Control tokens: 61,135
- Treatment tokens: 63,517
- Difference: +2,382 (inconclusive)

### Run 2 (2026-05-26)

| Session | Modern | Outdated | Total | Score |
|---------|--------|----------|-------|-------|
| Control (A) | 16 | 1 | 17 | 94.1% |
| Treatment (B) | 16 | 1 | 17 | 94.1% |
| **Improvement** | | | | **0pp** |

Outdated in both: P-04-2 (asyncio.gather)

Skill load verification:
- Physical: PASS (Control=ABSENT, Treatment=PRESENT)
- Control tokens: 61,350
- Treatment tokens: 63,050
- Difference: +1,700 (inconclusive)

### Run 3 (2026-05-26)

| Session | Modern | Outdated | Total | Score |
|---------|--------|----------|-------|-------|
| Control (A) | 16 | 1 | 17 | 94.1% |
| Treatment (B) | 17 | 0 | 17 | 100.0% |
| **Improvement** | | | | **+5.9pp** |

Outdated in Control: P-04-2 (asyncio.gather)
Treatment: perfect score (17/17)

Skill load verification:
- Physical: PASS (Control=ABSENT, Treatment=PRESENT)
- Control tokens: 61,218
- Treatment tokens: 67,488
- Difference: +6,270 (PASS)

## Aggregate

| Metric | Run 1 | Run 2 | Run 3 | Average |
|--------|-------|-------|-------|---------|
| Control score | 94.1% | 94.1% | 94.1% | 94.1% |
| Treatment score | 88.2% | 94.1% | 100.0% | 94.1% |
| Improvement | -5.9pp | 0pp | +5.9pp | 0pp |

### Key observations

1. **Control ceiling is very high (94.1%)**: Claude already generates Pydantic V2 modern patterns without SKILL.md. 16 of 17 items were consistently modern across all Control runs.
2. **P-04-2 (TaskGroup vs gather) is the only consistent gap**: All 3 Control runs used `asyncio.gather`. Only Treatment Run 3 used `TaskGroup`, suggesting SKILL.md's guidance is only visibly effective on this specific pattern.
3. **Net improvement is zero**: Treatment averaged the same as Control (94.1%). The positive effect in Run 3 was offset by the negative result in Run 1 (stochastic regression on P-03-3).
4. **Stochastic noise dominates**: Run 1 Treatment regressed on P-03-3 (Annotated), a pattern unrelated to SKILL.md's guidance direction. This indicates LLM output variance exceeds SKILL.md's signal.
5. **Physical verification passed all 6 sessions**: The skill toggle mechanism (rm/ln-s) is reliable.

## Limitations

- Single AI model (Claude). Results may differ with GPT, Gemini, etc.
- Small sample (N=3). Not statistically rigorous.
- Prompt wording affects results. Different phrasings may yield different patterns.
- Claude's training data evolves. Results are point-in-time.
- P-04-2 (TaskGroup vs gather) has a legitimate caveat — gather supports `return_exceptions=True` which TaskGroup does not.
