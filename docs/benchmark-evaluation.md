# Benchmark Evaluation

Issue: #8

## Hypothesis

Embedding BAD/GOOD patterns in SKILL.md (pre-generation injection) reduces outdated Python patterns in AI-generated code, particularly for patterns that Ruff cannot auto-fix.

---

## V2 Evaluation Checklist (13 items)

Prompt: `bench/prompt-v2.txt`

V1 tested mostly Pydantic V1→V2 API renames. Claude already knows them (94.1% baseline). V2 tests design-level patterns where the old way still compiles but is architecturally wrong. These are patterns where APILOT research shows pre-generation guidance has significant impact (avg 89.42% reduction in outdated recommendations).

### Coverage tiers

Items are grouped by SKILL.md coverage to measure the signal source:

- **Tier E (Embedded)**: Pattern + code example in SKILL.md embedded section → Treatment should improve
- **Tier G (Guide-listed)**: Guide name in SKILL.md "30 guides" list, no embedded example → might improve
- **Tier U (Uncovered)**: Not in SKILL.md at all → control group, no difference expected

### A: Structured Concurrency (1 item)

File: `src/crawler.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| A1 | E | `asyncio.gather()` | `asyncio.TaskGroup` | `TaskGroup` vs `gather` |

### F: FastAPI Architecture (3 items)

File: `src/app.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| F1 | E | `@app.on_event("startup"/"shutdown")` | lifespan context manager | `lifespan` vs `on_event` |
| F2 | E | `Depends()` without `Annotated` | `Annotated[..., Depends()]` | `Annotated\[` vs bare `Depends(` |
| F3 | U | `Depends()` for OAuth scopes | `Security()` with scopes | `Security(` |

### S: SQLAlchemy 2.0 (2 items)

File: `src/app.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| S1 | U | `session.query(User)` | `select(User)` + `session.scalars()` | `session.query` vs `select(` |
| S2 | U | sync `sessionmaker` in async | `async_sessionmaker` | `async_sessionmaker` |

### H: httpx (2 items)

File: `src/crawler.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| H1 | E | per-request `AsyncClient()` in loop | shared `AsyncClient` | `AsyncClient` present |
| H2 | U | manual retry loop only | `HTTPTransport(retries=)` | `HTTPTransport` |

Note: H2 scores whether the model knows HTTPTransport exists. Manual retry for HTTP-level errors is legitimate on top of transport retries.

### L: stdlib / typing (3 items)

| # | Tier | File | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|------|----------------|---------------|-------------|
| L1 | G | config.py | `import tomli` / `import toml` | `import tomllib` | `tomllib` |
| L2 | G | scanner.py | `os.walk()` | `Path.walk()` (3.12+) | `.walk(` in pathlib context vs `os.walk` |
| L3 | U | scanner.py | manual chunking loop | `itertools.batched()` (3.12+) | `batched` |

### T: Type system (1 item)

File: `src/config.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| T1 | G | `T = TypeVar("T")` + `Generic[T]` | PEP 695: `class Registry[T]:` | `TypeVar` vs `class.*\[` without TypeVar |

### M: match statement (1 item)

File: `src/scanner.py`

| # | Tier | Outdated (BAD) | Modern (GOOD) | grep detect |
|---|------|----------------|---------------|-------------|
| M1 | G | `case IMAGE:` (bare name = capture!) | `case FileCategory.IMAGE:` (qualified) | `case FileCategory\.` vs `case [A-Z][A-Z]` |

Note: In Python's structural pattern matching, bare names are always capture patterns — `case IMAGE:` captures the value into `IMAGE` rather than comparing against the constant. This is a real Python gotcha documented in PEP 636.

### Tier summary

| Tier | Items | Expected Treatment effect |
|------|-------|--------------------------|
| E (Embedded) | A1, F1, F2, H1 | Strong improvement |
| G (Guide-listed) | L1, L2, T1, M1 | Possible improvement |
| U (Uncovered) | F3, S1, S2, H2, L3 | No improvement (control) |

## Scoring

| Metric | Formula |
|--------|---------|
| Modern patterns | Count of GOOD patterns detected |
| Outdated patterns | Count of BAD patterns detected |
| Score | `modern / 13 * 100` (%) |
| Improvement | Treatment score - Control score (pp) |
| Tier E improvement | Treatment Tier E score - Control Tier E score |
| Tier G improvement | Treatment Tier G score - Control Tier G score |
| Tier U improvement | Treatment Tier U score - Control Tier U score (expected: ~0) |

All 13 patterns are Ruff-uncoverable, so any improvement is attributable to SKILL.md.

## Interpretation

| Improvement | Meaning | Action |
|-------------|---------|--------|
| 0-10pp overall | Marginal | Reconsider product positioning |
| 10-30pp overall | Moderate | Strengthen SKILL.md, add more patterns |
| 30pp+ overall | Strong | Double down on SKILL.md approach |

### Tier-level interpretation

| Outcome | Meaning |
|---------|---------|
| Tier E improves, U flat | SKILL.md embedded patterns work |
| Tier G improves, U flat | SKILL.md guide listing alone has value |
| Tier E+G flat, U flat | SKILL.md has no measurable effect |
| Tier U also improves | Confound — skill toggle may not be working |

## Design decisions (V2-specific)

### Why V2 dropped Pydantic items

V1's 11 Pydantic items (P-01, P-02) were API renames: `@validator` → `@field_validator`, `.dict()` → `.model_dump()`, etc. Claude scored 94.1% on these without any guidance. Pydantic V2 was released in June 2023 and is now well-represented in training data. These items have no room for SKILL.md to add value.

### Why V2 adds SQLAlchemy, match, stdlib items

The deep research identified that AI consistently falls back to old patterns when:
1. The old API is backward-compatible and still works (e.g., `session.query()`)
2. The new feature was introduced recently with low adoption (e.g., `itertools.batched`, PEP 695)
3. The pattern involves a design decision, not a syntax swap (e.g., `Security()` vs `Depends()`)

### Three-tier design

Grouping items by SKILL.md coverage tier allows causal attribution. If only Tier E and G improve while Tier U stays flat, the improvement is attributable to SKILL.md content, not confounds like cache or session ordering.

### Prompt contains no evaluation criteria

`bench/prompt-v2.txt` contains only generation instructions — no BAD/GOOD hints, no "modern" or "best practice" keywords. Target Python version (3.12+) is stated only in the pyproject.toml spec.

---

## V1 Evaluation Checklist (17 items) — archived

Prompt: `bench/prompt.txt`

### V1 items (collapsed)

| Category | Items | File |
|----------|-------|------|
| P-01: Pydantic model | 6 (validators, Config, orm_mode, dict) | models.py |
| P-02: Pydantic serialization | 5 (parse_obj, parse_raw, json, schema, copy) | serialization.py |
| P-03: FastAPI lifecycle | 3 (on_event, Annotated Depends) | app.py |
| P-04: Async HTTP | 2 (AsyncClient, TaskGroup) | fetcher.py |
| P-05: Subprocess | 1 (shell=True) | runner.py |
| **Total** | **17** | |

P-05-1 excluded: prompt asks for pyproject.toml explicitly.

## V2 Results

### V2 Run 4 (2026-05-26)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | OUTDATED |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | MODERN | OUTDATED |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | OUTDATED | OUTDATED |
| T1 | G | PEP 695 generics | OUTDATED | OUTDATED |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 9/13 | 8/13 |
| Score | 69.2% | 61.5% |
| Tier E (4) | 3/4 | 2/4 |
| Tier G (4) | 3/4 | 3/4 |
| Tier U (5) | 3/5 | 3/5 |

### V2 Run 5 (2026-05-26)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | OUTDATED |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | MODERN | OUTDATED |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | MODERN | MODERN |
| T1 | G | PEP 695 generics | OUTDATED | OUTDATED |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 10/13 | 9/13 |
| Score | 76.9% | 69.2% |
| Tier E (4) | 3/4 | 2/4 |
| Tier G (4) | 3/4 | 3/4 |
| Tier U (5) | 4/5 | 4/5 |

### V2 Run 6 (2026-05-26)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | OUTDATED |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | MODERN | MODERN |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | OUTDATED | OUTDATED |
| T1 | G | PEP 695 generics | OUTDATED | OUTDATED |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 9/13 | 9/13 |
| Score | 69.2% | 69.2% |
| Tier E (4) | 3/4 | 3/4 |
| Tier G (4) | 3/4 | 3/4 |
| Tier U (5) | 3/5 | 3/5 |

### V2 Runs 4-6 Aggregate (INVALID — skill not loaded)

| Metric | Run 4 | Run 5 | Run 6 | Average |
|--------|-------|-------|-------|---------|
| Control score | 69.2% | 76.9% | 69.2% | 71.8% |
| Treatment score | 61.5% | 69.2% | 69.2% | 66.6% |
| Improvement | -7.7pp | -7.7pp | 0pp | -5.1pp |
| Tier E improvement | -1 | -1 | 0 | -0.7 |
| Tier G improvement | 0 | 0 | 0 | 0 |
| Tier U improvement | 0 | 0 | 0 | 0 |

### V2 Runs 4-6 Key observations (skill-based — INVALID)

**Root cause**: SKILL.md body is NOT loaded in `claude -p` (pipe mode). Skills are deferred/on-demand — the body is only loaded when the Skill tool is explicitly invoked. In pipe mode, Claude never self-invokes skills. Token analysis showed no increase between Control and Treatment, confirming the guidance was absent in all 6 Treatment sessions.

These runs are invalid as A/B tests. Both Control and Treatment ran without guidance.

### V2 Run 7 (2026-05-26, rules-based toggle)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | MODERN |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | MODERN | MODERN |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | OUTDATED | MODERN |
| T1 | G | PEP 695 generics | OUTDATED | MODERN |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 10/13 | 12/13 |
| Score | 76.9% | 92.3% |
| Tier E (4) | 3/4 | 4/4 |
| Tier G (4) | 3/4 | 4/4 |
| Tier U (5) | 4/5 | 4/5 |

Token diff: +1,834 (PASS). Physical verification: PASS.

### V2 Run 8 (2026-05-26, rules-based toggle)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | MODERN |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | MODERN | MODERN |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | MODERN | MODERN |
| T1 | G | PEP 695 generics | OUTDATED | MODERN |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 10/13 | 12/13 |
| Score | 76.9% | 92.3% |
| Tier E (4) | 3/4 | 4/4 |
| Tier G (4) | 3/4 | 4/4 |
| Tier U (5) | 4/5 | 4/5 |

Token diff: +1,143 (PASS). Physical verification: PASS.

### V2 Run 9 (2026-05-26, rules-based toggle)

| # | Tier | Pattern | Control | Treatment |
|---|------|---------|---------|-----------|
| A1 | E | TaskGroup vs gather | OUTDATED | MODERN |
| F1 | E | lifespan vs on_event | MODERN | MODERN |
| F2 | E | Annotated Depends | OUTDATED | MODERN |
| F3 | U | Security() for OAuth | MODERN | MODERN |
| S1 | U | select() vs query() | MODERN | MODERN |
| S2 | U | async_sessionmaker | MODERN | MODERN |
| H1 | E | shared AsyncClient | MODERN | MODERN |
| H2 | U | HTTPTransport | OUTDATED | OUTDATED |
| L1 | G | tomllib | MODERN | MODERN |
| L2 | G | Path.walk() | MODERN | MODERN |
| L3 | U | itertools.batched() | OUTDATED | MODERN |
| T1 | G | PEP 695 generics | OUTDATED | MODERN |
| M1 | G | qualified match names | MODERN | MODERN |

| Metric | Control | Treatment |
|--------|---------|-----------|
| Modern | 8/13 | 12/13 |
| Score | 61.5% | 92.3% |
| Tier E (4) | 2/4 | 4/4 |
| Tier G (4) | 3/4 | 4/4 |
| Tier U (5) | 3/5 | 4/5 |

Token diff: +1,229 (PASS). Physical verification: PASS.

### V2 Rules-based Aggregate (Runs 7-9)

| Metric | Run 7 | Run 8 | Run 9 | Average |
|--------|-------|-------|-------|---------|
| Control score | 76.9% | 76.9% | 61.5% | 71.8% |
| Treatment score | 92.3% | 92.3% | 92.3% | 92.3% |
| Improvement | +15.4pp | +15.4pp | +30.8pp | **+20.5pp** |
| Tier E improvement | +1 | +1 | +2 | +1.3 |
| Tier G improvement | +1 | +1 | +1 | +1.0 |
| Tier U improvement | 0 | 0 | +1 | +0.3 |

### V2 Key observations (rules-based, Runs 7-9)

1. **Guidance delivery fixed**: Moving content from `skills/` (deferred/on-demand) to `.claude/rules/` (always-loaded) resolved the root cause. Token analysis confirms +1,143 to +1,834 token increase in Treatment sessions.
2. **Consistent +20.5pp improvement**: Treatment averaged 92.3% across all 3 runs (zero variance). Control varied from 61.5% to 76.9% (stochastic).
3. **A1 (TaskGroup) flipped in all 3 runs**: The hardest pattern in Runs 4-6 (never achieved) became consistently MODERN with guidance. This is the strongest single-item signal.
4. **T1 (PEP 695) flipped in all 3 runs**: TypeVar → PEP 695 syntax conversion is reliably triggered by the guide listing alone (Tier G).
5. **L3 (itertools.batched) improved**: 2 of 3 Treatment runs used `batched()`, up from 1 of 3 Controls. As a Tier U item, this may be spillover from general "modern stdlib" priming.
6. **H2 (HTTPTransport) remains the only unachieved item**: 0/6 sessions used it. This Tier U control group item confirms the guidance isn't causing false positive improvements.
7. **Tier analysis confirms causal attribution**: Tier E (+1.3 avg) and Tier G (+1.0 avg) show clear improvement. Tier U (+0.3 avg) is near-zero, confirming the effect comes from SKILL.md content, not confounds.
8. **F2 stochastic noise resolved**: Runs 4-6 showed F2 (Annotated Depends) regression in Treatment. With guidance actually loaded (Runs 7-9), F2 is consistently MODERN in Treatment.

---

## V1 Results

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
- Small sample (N=3 per version). Not statistically rigorous.
- Prompt wording affects results. Different phrasings may yield different patterns.
- Claude's training data evolves. Results are point-in-time.
- A1 (TaskGroup vs gather) has a legitimate caveat — gather supports `return_exceptions=True` which TaskGroup does not.
- H2 (HTTPTransport) only handles ConnectError/ConnectTimeout. Manual retry for HTTP-level errors is legitimate.
- M1 (match qualified names) grep detection is fragile — depends on AI's naming choices.
- T1 (PEP 695) checker support is still maturing — some toolchains don't fully support it yet.

## Prompt versioning

| Version | Date | Items | Delivery | Changes |
|---------|------|-------|----------|---------|
| v1 | 2026-05-26 | 17 | skills/ (broken) | Initial. 6 files, Pydantic V1 terms as stress test |
| v2 Runs 4-6 | 2026-05-26 | 13 | skills/ (broken) | Redesign. Dropped Pydantic renames, added SQLAlchemy/match/stdlib. Three-tier coverage. **INVALID**: skill body not loaded in pipe mode |
| v2 Runs 7-9 | 2026-05-26 | 13 | rules/ (fixed) | Same prompt as v2. Toggle via `.claude/rules/modern-python.md` create/delete. **VALID**: +20.5pp avg improvement |
