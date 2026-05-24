---
id: ruff-over-flake8
title: Use Ruff Instead of Flake8 + isort + Black
category: toolchain
layer: 3
tags:
  - ruff
  - linting
  - formatting
  - flake8
  - isort
  - black
aliases:
  - flake8
  - isort
  - black
  - ruff
  - linter
  - formatter
python: ">=3.7"
frequency: high
---

# Use Ruff Instead of Flake8 + isort + Black

Ruff replaces Flake8, isort, Black, pyupgrade, and dozens of other tools in a single Rust binary.

## BAD

```toml
# pyproject.toml — multiple tools to configure separately
[tool.flake8]
max-line-length = 88

[tool.isort]
profile = "black"

[tool.black]
line-length = 88
target-version = ["py311"]
```

```bash
flake8 src/
isort src/
black src/
```

## GOOD

```toml
# pyproject.toml — single tool
[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.ruff.format]
docstring-code-format = true
```

```bash
ruff check src/ --fix
ruff format src/
```

## Why

- 10-100x faster than Flake8 (Rust implementation)
- Single tool replaces Flake8, isort, Black, pyupgrade, pydocstyle, and 50+ plugins
- `--fix` auto-fixes most lint violations
- `ruff format` is a drop-in replacement for Black
- Configured entirely in `pyproject.toml`

## Rule Selection Guide

| Rule prefix | Replaces | Purpose |
|-------------|----------|---------|
| `E`, `F` | Flake8 (pycodestyle + pyflakes) | Core errors and style |
| `I` | isort | Import sorting |
| `UP` | pyupgrade | Python version upgrades |
| `B` | flake8-bugbear | Common bug patterns |
| `SIM` | flake8-simplify | Code simplification |

## References

- [Ruff documentation](https://docs.astral.sh/ruff/)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
