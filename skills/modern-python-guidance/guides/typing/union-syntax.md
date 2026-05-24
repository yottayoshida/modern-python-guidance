---
id: union-syntax
title: Use X | Y Union Syntax Instead of Optional/Union
category: typing
layer: 1
tags:
  - type-hints
  - union
  - optional
aliases:
  - Optional
  - typing.Union
  - typing.Optional
python: ">=3.10"
frequency: high
pep: 604
---

# Use X | Y Union Syntax

Since Python 3.10, use the `|` operator for union types instead of `Union` or `Optional` from `typing`.

## BAD

```python
from typing import Optional, Union

def find(name: str) -> Optional[int]:
    ...

def parse(value: Union[str, int, float]) -> str:
    ...
```

## GOOD

```python
def find(name: str) -> int | None:
    ...

def parse(value: str | int | float) -> str:
    ...
```

## Why

- Shorter, more readable syntax
- `Optional[X]` is just `Union[X, None]` — the new syntax makes `None` explicit
- Works in `isinstance()` checks too: `isinstance(x, str | int)`
- `Union` and `Optional` are deprecated since 3.10

## Version Notes

- 3.10+: `X | Y` in annotations and `isinstance()`/`issubclass()`
- 3.9: Use `from __future__ import annotations` for deferred evaluation only

## References

- [PEP 604 — Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
