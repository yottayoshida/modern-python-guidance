# Manual Benchmark Procedure

Since `claude -p` consumes credits (as of 2026-06-15), run benchmarks manually inside subscription sessions instead of using `run-v5.sh`.

## Overview

| Step | What | Where |
|------|------|-------|
| 1 | Prepare result directories | Terminal |
| 2 | Run control sessions (no guidance) | Claude Code subscription session |
| 3 | Run treatment sessions (with guidance) | Claude Code subscription session |
| 4 | Score results | Terminal (Python 3.12+, local only) |

## Quick Start (terse / variant-a / N=3)

This is the standard configuration used in recent benchmarks.

### Step 1: Prepare directories

```bash
cd ~/claude_workspace/modern-python-guidance

RUN_TAG="YYYYMMDD"  # e.g. 20260615
for n in 1 2 3; do
  mkdir -p "results/run-${RUN_TAG}-${n}-v5at/{control,treatment}"
done
```

### Step 2: Control sessions (no guidance)

Run 3 separate Claude Code sessions, each in a clean tmpdir with **no** `.claude/rules/modern-python.md`.

For each run (n = 1, 2, 3):

```bash
# Create isolated workspace
tmpdir=$(mktemp -d "$HOME/mpg-bench-XXXXXX")
cd "$tmpdir"
claude
```

Paste this prompt in the session:

> Build a FastAPI web application with an async web crawler. Use SQLAlchemy for the database, httpx for HTTP requests, Pydantic for data validation, and TOML for configuration. Include a file scanner utility with pattern matching. Target Python 3.12+. Write all code with no placeholders.

After generation completes, exit the session and collect files:

```bash
RUN_TAG="YYYYMMDD"  # same tag as Step 1
n=1                  # increment for each run

# Copy generated files (exclude .claude/)
rsync -a --exclude='.claude' "$tmpdir/" \
  ~/claude_workspace/modern-python-guidance/results/run-${RUN_TAG}-${n}-v5at/control/

rm -rf "$tmpdir"
```

### Step 3: Treatment sessions (with guidance)

Same as Step 2, but inject the guidance file before starting Claude Code:

```bash
tmpdir=$(mktemp -d "$HOME/mpg-bench-XXXXXX")
mkdir -p "$tmpdir/.claude/rules"

# Extract guidance content (strips YAML frontmatter)
awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' \
  ~/claude_workspace/modern-python-guidance/skills/modern-python-guidance/SKILL.md \
  > "$tmpdir/.claude/rules/modern-python.md"

cd "$tmpdir"
claude
```

Paste the **same prompt** as control. Collect files to `treatment/` instead:

```bash
rsync -a --exclude='.claude' "$tmpdir/" \
  ~/claude_workspace/modern-python-guidance/results/run-${RUN_TAG}-${n}-v5at/treatment/

rm -rf "$tmpdir"
```

### Step 4: Score

```bash
cd ~/claude_workspace/modern-python-guidance

for n in 1 2 3; do
  echo "=== Run $n ==="
  python3 bench/score_v5.py "${RUN_TAG}-${n}-v5at" --variant a
  echo
done
```

JSON output (for aggregation):

```bash
python3 bench/score_v5.py "${RUN_TAG}-1-v5at" --variant a --format json
```

## Other Variants / Granularities

### Prompts

| Variant | Granularity | File | Domain |
|---------|-------------|------|--------|
| a | terse | `prompts/v5-a-terse.txt` | FastAPI + httpx + SQLAlchemy |
| a | normal | `prompts/v5-a-normal.txt` | FastAPI + httpx + SQLAlchemy |
| a | detailed | `prompts/v5-a-detailed.txt` | FastAPI + httpx + SQLAlchemy |
| b | terse | `prompts/v5-b-terse.txt` | Django |
| b | normal | `prompts/v5-b-normal.txt` | Django |
| b | detailed | `prompts/v5-b-detailed.txt` | Django |
| c | terse | `prompts/v5-c-terse.txt` | pytest |
| c | normal | `prompts/v5-c-normal.txt` | pytest |
| c | detailed | `prompts/v5-c-detailed.txt` | pytest |

### Run ID convention

```
results/run-{RUN_TAG}-{n}-v5{variant}{granularity_initial}/
```

Examples:
- `run-20260615-1-v5at` → variant a, terse, run 1
- `run-20260615-2-v5bn` → variant b, normal, run 2
- `run-20260615-1-v5cd` → variant c, detailed, run 1

### Scorer variant flag

Always pass `--variant` matching the prompt:

```bash
python3 bench/score_v5.py "20260615-1-v5bn" --variant b
```

## Model Override

To benchmark a specific model, start Claude Code with `--model`:

```bash
cd "$tmpdir"
claude --model claude-sonnet-4-6
```

Record the model in the run tag for traceability (e.g. `sonnet46-1-v5at`).

## Checklist

- [ ] Control: `.claude/rules/modern-python.md` must NOT exist in tmpdir
- [ ] Treatment: `.claude/rules/modern-python.md` must exist (extracted from SKILL.md)
- [ ] Same prompt for both control and treatment
- [ ] Same model for both control and treatment
- [ ] tmpdir cleaned up after file collection
- [ ] Scorer runs on Python 3.12+
