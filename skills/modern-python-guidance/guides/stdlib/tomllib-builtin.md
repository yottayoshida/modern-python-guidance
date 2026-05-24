---
id: tomllib-builtin
title: Use Built-in tomllib Instead of Third-Party toml
category: stdlib
layer: 1
tags:
  - toml
  - config
  - stdlib
aliases:
  - toml
  - tomli
  - tomllib
python: ">=3.11"
frequency: medium
pep: 680
---

# Use Built-in tomllib

Since Python 3.11, use the built-in `tomllib` module for reading TOML files instead of third-party packages like `toml` or `tomli`.

## BAD

```python
import toml  # third-party, unmaintained

with open("pyproject.toml") as f:
    config = toml.load(f)
```

## GOOD

```python
import tomllib

with open("pyproject.toml", "rb") as f:
    config = tomllib.load(f)

# Or from a string:
config = tomllib.loads(toml_string)
```

## Why

- No external dependency needed for TOML reading
- `tomllib` is TOML 1.0 compliant
- Based on `tomli` (battle-tested implementation adopted into stdlib)
- Read-only by design — use `tomli-w` or `tomlkit` for writing

## Version Notes

- 3.11+: `import tomllib`
- Pre-3.11: `pip install tomli` (same API as `tomllib`)
- `tomllib.load()` requires binary mode (`"rb"`), not text mode

## References

- [PEP 680 — tomllib: Support for Parsing TOML in the Standard Library](https://peps.python.org/pep-0680/)
