# Effectiveness Benchmark: Pre-generation Guidance vs No Guidance

Issue: #8

## Hypothesis

Embedding BAD/GOOD patterns in SKILL.md (pre-generation injection) reduces outdated Python patterns in AI-generated code, particularly for patterns that Ruff cannot auto-fix.

## Method

A/B comparison across two Claude Code sessions:

| Condition | Setup |
|-----------|-------|
| **A (Control)** | Fresh session, no SKILL.md loaded. Default Claude Code behavior |
| **B (Treatment)** | Fresh session, `modern-python-guidance` skill installed and triggered |

Each prompt is given identically to both sessions. Generated code is scored for outdated pattern usage.

### How to run

1. **Session A (no guidance)**: Start a new Claude Code session in a Python project that does NOT have `modern-python-guidance` skill installed. Run each prompt below verbatim.
2. **Session B (with guidance)**: Start a new Claude Code session in a Python project that HAS the skill installed (symlinked to `.claude/skills/`). Run each prompt below verbatim.
3. Record the generated code and score using the evaluation rubric.

### Important controls

- Do NOT mention "modern", "best practice", "latest", or "up to date" in prompts
- Use identical Python version context (3.11+ in pyproject.toml)
- Each session should be fresh (no conversation history)

---

## Test Prompts

### P-01: Pydantic model with validators (targets: @validator, Config class, .dict())

```
Write a Pydantic model called `UserProfile` with fields: name (str, must be capitalized),
email (str, must contain @), age (int, must be 18+). Add a validator for each field.
Include a Config class that enables ORM mode and allows population by field name.
Add a method that returns the model as a dictionary.
```

**Outdated patterns to detect**:
- [ ] `@validator` instead of `@field_validator`
- [ ] `@root_validator` instead of `@model_validator`
- [ ] `class Config:` instead of `model_config = ConfigDict(...)`
- [ ] `orm_mode = True` instead of `from_attributes = True`
- [ ] `allow_population_by_field_name` instead of `populate_by_name`
- [ ] `.dict()` instead of `.model_dump()`

### P-02: Pydantic serialization and parsing (targets: parse_obj, parse_raw, .json(), .schema())

```
Write a function that:
1. Creates a Pydantic model `Order` with fields: id (int), items (list of str), total (float)
2. Parses an Order from a dict
3. Parses an Order from a JSON string
4. Serializes an Order to JSON
5. Gets the JSON schema of Order
6. Creates a copy of an Order with a modified total
```

**Outdated patterns to detect**:
- [ ] `.parse_obj()` instead of `.model_validate()`
- [ ] `.parse_raw()` instead of `.model_validate_json()`
- [ ] `.json()` instead of `.model_dump_json()`
- [ ] `.schema()` instead of `.model_json_schema()`
- [ ] `.copy()` instead of `.model_copy()`

### P-03: FastAPI app with startup/shutdown (targets: on_event, Depends)

```
Write a FastAPI app with:
1. A startup event that initializes a database connection pool
2. A shutdown event that closes the pool
3. A dependency that provides a database session
4. Three endpoints that use the database dependency: GET /users, GET /users/{id}, POST /users
```

**Outdated patterns to detect**:
- [ ] `@app.on_event("startup")` instead of lifespan context manager
- [ ] `@app.on_event("shutdown")` instead of lifespan context manager
- [ ] `Depends(get_db)` without `Annotated[]` type alias

### P-04: Async HTTP client (targets: per-request client, gather)

```
Write an async function that fetches data from 3 different API endpoints concurrently
and returns the combined results. Use httpx for HTTP requests.
The function should handle timeouts and errors gracefully.
```

**Outdated patterns to detect**:
- [ ] Per-request `async with httpx.AsyncClient()` instead of shared client
- [ ] `asyncio.gather()` instead of `TaskGroup`

### P-05: Project setup and subprocess (targets: setup.py, shell=True)

```
Write a Python script that:
1. Shows a pyproject.toml configuration for a library called "mylib" with dependencies on
   requests and click, supporting Python 3.11+
2. Includes a function that runs an external command with a user-provided filename argument
```

**Outdated patterns to detect**:
- [ ] `setup.py` / `setup.cfg` instead of `pyproject.toml`
- [ ] `subprocess.run(f"cmd {arg}", shell=True)` instead of list form

---

## Evaluation Rubric

For each prompt, count:

| Metric | Definition |
|--------|-----------|
| **Outdated patterns** | Number of checked boxes (BAD patterns used) |
| **Modern patterns** | Number of unchecked boxes (GOOD patterns used) |
| **Total checkpoints** | Total items in the checklist |
| **Score** | `modern / total * 100` (higher = better) |

### Aggregate scoring

| Metric | Formula |
|--------|--------|
| **Control score** | Average score across P-01 to P-05 (Session A) |
| **Treatment score** | Average score across P-01 to P-05 (Session B) |
| **Improvement** | Treatment score - Control score |
| **Ruff-uncoverable improvement** | Same calculation, excluding patterns Ruff can auto-fix |

### Which patterns can Ruff auto-fix?

Of the patterns tested, only these have Ruff equivalents:
- `use-builtin-generics` (UP006) — not tested here (already well-known)
- `union-syntax` (UP007) — not tested here

All patterns in P-01 through P-05 are **Ruff-uncoverable**, making any improvement attributable entirely to mpg.

---

## Results Template

### Session A (Control — no guidance)

| Prompt | Outdated | Modern | Total | Score |
|--------|----------|--------|-------|-------|
| P-01 | | | 6 | |
| P-02 | | | 5 | |
| P-03 | | | 3 | |
| P-04 | | | 2 | |
| P-05 | | | 2 | |
| **Total** | | | **18** | |

### Session B (Treatment — with SKILL.md)

| Prompt | Outdated | Modern | Total | Score |
|--------|----------|--------|-------|-------|
| P-01 | | | 6 | |
| P-02 | | | 5 | |
| P-03 | | | 3 | |
| P-04 | | | 2 | |
| P-05 | | | 2 | |
| **Total** | | | **18** | |

### Summary

| Metric | Value |
|--------|-------|
| Control score | % |
| Treatment score | % |
| Improvement | +pp |
| Patterns tested | 18 |
| Ruff-coverable patterns | 0 |
| Ruff-uncoverable improvement | +pp |

### Observations

(Free-form notes on qualitative differences: code style, comments, caveats mentioned, etc.)

---

## Interpreting Results

| Improvement | Interpretation | Action |
|------------|----------------|--------|
| **0-10pp** | Marginal. Pre-generation guidance has little effect | Reconsider product positioning |
| **10-30pp** | Moderate. Guidance helps but AI already knows some patterns | Strengthen SKILL.md patterns, add more |
| **30pp+** | Strong. Pre-generation guidance significantly improves output | Double down on SKILL.md approach |

## Limitations

- Single AI model (Claude). Results may differ with GPT, Gemini, etc.
- Small sample (5 prompts). Not statistically rigorous.
- Prompt wording affects results. Different phrasings may yield different patterns.
- Claude's training data evolves. Results are point-in-time (tested: YYYY-MM-DD).
