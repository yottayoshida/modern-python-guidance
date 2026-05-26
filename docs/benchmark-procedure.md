# Benchmark Procedure

Issue: #8

## Overview

A/B test measuring whether SKILL.md pre-generation guidance reduces outdated Python patterns in AI-generated code.

- **Control (A)**: SKILL.md disabled — default Claude Code behavior
- **Treatment (B)**: SKILL.md enabled — modern-python-guidance skill active

## Prerequisites

1. Claude Code CLI (`claude`) installed and authenticated
2. `modern-python-guidance` skill symlinked to `~/.claude/skills/modern-python-guidance`
3. No other Python-focused skills installed that could interfere

## Running the benchmark

```bash
cd ~/claude_workspace/modern-python-guidance

# Run with default run_id=1
./bench/run.sh

# Or specify a run_id for repeated runs
./bench/run.sh 1
./bench/run.sh 2
./bench/run.sh 3
```

### What run.sh does

1. Verifies the skill directory exists
2. **Session A (Control)**: Moves the skill directory to `.__disabled__` (disabling it), runs `claude -p` with the prompt, captures generated code + JSON output
3. **Session B (Treatment)**: Restores the skill directory, runs `claude -p` again, captures results
4. Uses `trap EXIT` to restore the skill even if the script fails

### Output

```
results/run-<N>/
  session-a.json       # CC output with usage info (Control)
  session-b.json       # CC output with usage info (Treatment)
  session-a.stderr     # stderr from Control session
  session-b.stderr     # stderr from Treatment session
  control/src/         # Generated code without skill
  treatment/src/       # Generated code with skill
```

## Scoring

```bash
./bench/score.sh 1    # Score run 1
```

The scorer:
- Checks 17 pattern items via grep (P-05-1 excluded, see below)
- Reports modern vs outdated pattern counts per session
- Verifies skill loading via `cache_creation_input_tokens` difference

For the full evaluation criteria, see `docs/benchmark-evaluation.md`.

## Design decisions

### V1 terminology is intentional

The prompt uses Pydantic V1 terms like "Config class", "ORM mode", and "population by field name." This is deliberate — the test measures whether the AI translates these to V2 equivalents. Without SKILL.md guidance, the AI may follow the prompt's V1 terminology literally.

### P-05-1 excluded (17 items, not 18)

The prompt explicitly asks for `pyproject.toml`. Testing whether the AI chooses `setup.py` when told to create `pyproject.toml` is meaningless. This item is excluded from scoring.

### Prompt contains no evaluation criteria

`bench/prompt.txt` contains only generation instructions — no BAD/GOOD hints, no "modern" or "best practice" keywords. The evaluation criteria live separately in `docs/benchmark-evaluation.md` to prevent answer leakage.

### Skill toggle via mv

`skillOverrides` in Claude Code settings is broken (GitHub Issue #50631). The `mv` approach reliably toggles the skill by renaming its directory.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `claude -p` hangs | Budget too low | Increase `--max-budget-usd` in run.sh |
| No files in control/src/ | CC didn't create files | Check session-a.stderr. Try running manually |
| score.sh shows all NOT FOUND | Files in wrong directory | Check if CC wrote to a different path |
| Skill load verification WARN | Skill may not have triggered | Check if prompt contains trigger keywords |
| `ERROR: Results directory already exists` | Previous run exists | Use a different run_id or remove the directory |

## Prompt versioning

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-05-26 | Initial 6-file prompt. V1 terms retained as stress test |
