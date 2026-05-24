---
id: uv-over-pip
title: Use uv Instead of pip for Package Management
category: toolchain
layer: 3
tags:
  - uv
  - pip
  - packaging
  - virtual-env
aliases:
  - pip install
  - pip
  - uv
  - virtualenv
  - venv
python: ">=3.8"
frequency: high
---

# Use uv Instead of pip

`uv` is a drop-in replacement for `pip`, `pip-tools`, `virtualenv`, and `pyenv` — written in Rust, 10-100x faster.

## BAD

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
pip freeze > requirements.txt
```

## GOOD

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e ".[dev]"

# Or use uv's project workflow (pyproject.toml-native)
uv init my-project
uv add requests httpx
uv add --dev pytest ruff
uv run pytest
uv lock
```

## Why

- 10-100x faster than pip (Rust implementation with global cache)
- Replaces pip, pip-tools, virtualenv, pyenv in a single binary
- `uv.lock` provides reproducible, cross-platform lockfiles
- `uv run` auto-creates virtualenv and installs dependencies
- Compatible with existing `requirements.txt` and `pyproject.toml`

## Version Notes

- `uv` is a third-party tool by Astral (same team as Ruff)
- Works with Python 3.8+
- `uv init` generates `pyproject.toml` (PEP 621 compliant)

## References

- [uv documentation](https://docs.astral.sh/uv/)
- [uv GitHub](https://github.com/astral-sh/uv)
