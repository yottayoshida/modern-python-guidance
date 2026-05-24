---
id: pathlib-over-os-path
title: Use pathlib.Path Instead of os.path
category: stdlib
layer: 1
tags:
  - pathlib
  - filesystem
  - os.path
aliases:
  - os.path
  - os.path.join
  - os.path.exists
python: ">=3.9"
frequency: high
---

# Use pathlib.Path Instead of os.path

Use `pathlib.Path` for filesystem operations instead of string-based `os.path` functions.

## BAD

```python
import os

config_path = os.path.join(os.path.expanduser("~"), ".config", "app", "config.toml")
if os.path.exists(config_path):
    with open(config_path) as f:
        data = f.read()

parent = os.path.dirname(config_path)
name = os.path.basename(config_path)
ext = os.path.splitext(config_path)[1]
```

## GOOD

```python
from pathlib import Path

config_path = Path.home() / ".config" / "app" / "config.toml"
if config_path.exists():
    data = config_path.read_text()

parent = config_path.parent
name = config_path.name
ext = config_path.suffix
```

## Why

- `/` operator for path joining is more readable than `os.path.join`
- Methods on Path objects instead of free functions on strings
- Built-in `read_text()`, `write_text()`, `read_bytes()`, `write_bytes()`
- Type safety — `Path` vs raw `str` catches path/string confusion
- `os.path` functions still work with `Path` objects (backwards compatible)

## Version Notes

- 3.4+: `pathlib.Path` available
- 3.6+: `os` functions accept `Path` objects
- 3.9+: `Path.with_stem()`, `Path.is_relative_to()`
- 3.12+: `Path.walk()` replaces `os.walk()`

## References

- [pathlib documentation](https://docs.python.org/3/library/pathlib.html)
