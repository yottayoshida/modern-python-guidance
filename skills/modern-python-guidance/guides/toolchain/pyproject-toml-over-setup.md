---
id: pyproject-toml-over-setup
title: Use pyproject.toml Instead of setup.py
category: toolchain
layer: 3
tags:
  - packaging
  - pyproject
  - setup.py
  - build
aliases:
  - setup.py
  - setup.cfg
  - setuptools
python: ">=3.7"
frequency: high
pep: 621
---

# Use pyproject.toml Instead of setup.py

PEP 621 standardizes project metadata in `pyproject.toml`. `setup.py` and `setup.cfg` are legacy.

## BAD

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="my-package",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["requests>=2.28"],
    python_requires=">=3.11",
)
```

## GOOD

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-package"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.28"]
```

## Why

- `setup.py` executes arbitrary code at install time (security risk)
- `pyproject.toml` is declarative and statically analyzable
- All modern tools (pip, uv, hatch, flit, PDM) support PEP 621
- `setup.py` is no longer needed for pure-Python packages

## Version Notes

- PEP 621 is supported by pip since 21.3 (2021-10)
- Python version doesn't matter — this is a tooling decision

## References

- [PEP 621 — Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- [PEP 517 — Build system interface](https://peps.python.org/pep-0517/)
