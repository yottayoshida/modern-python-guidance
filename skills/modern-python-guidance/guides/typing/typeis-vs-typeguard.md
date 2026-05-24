---
id: typeis-vs-typeguard
title: Use TypeIs for Precise Type Narrowing
category: typing
layer: 1
tags:
  - type-hints
  - narrowing
  - typeguard
aliases:
  - TypeGuard
  - typing.TypeGuard
  - typing.TypeIs
python: ">=3.13"
frequency: low
pep: 742
---

# Use TypeIs for Precise Type Narrowing

Since Python 3.13, use `TypeIs` instead of `TypeGuard` for type narrowing functions. `TypeIs` narrows in both branches (true and false), while `TypeGuard` only narrows in the true branch.

## BAD

```python
from typing import TypeGuard

def is_str(val: str | int) -> TypeGuard[str]:
    return isinstance(val, str)

def process(val: str | int) -> None:
    if is_str(val):
        print(val.upper())  # OK: narrowed to str
    else:
        print(val + 1)  # ERROR: still str | int, not narrowed to int
```

## GOOD

```python
from typing import TypeIs

def is_str(val: str | int) -> TypeIs[str]:
    return isinstance(val, str)

def process(val: str | int) -> None:
    if is_str(val):
        print(val.upper())  # OK: narrowed to str
    else:
        print(val + 1)  # OK: narrowed to int
```

## Why

- `TypeIs` narrows both branches — the false branch gets the complement type
- `TypeGuard` was too permissive — it could widen types unsoundly
- Safer and more precise for runtime type checking functions

## Version Notes

- 3.13+: `from typing import TypeIs`
- 3.10-3.12: `from typing_extensions import TypeIs`

## References

- [PEP 742 — Narrowing types with TypeIs](https://peps.python.org/pep-0742/)
