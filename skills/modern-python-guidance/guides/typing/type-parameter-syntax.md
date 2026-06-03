---
id: type-parameter-syntax
title: Use PEP 695 Type Parameter Syntax for Generics
category: typing
layer: 1
tags:
  - type-hints
  - generics
  - typevar
aliases:
  - TypeVar
  - typing.TypeVar
  - type alias
python: ">=3.12"
frequency: medium
pep: 695
detect-patterns:
  - "from typing import .*\bGeneric\b"
---

# Use PEP 695 Type Parameter Syntax

Since Python 3.12, use the bracket syntax for type parameters instead of `TypeVar`, `TypeVarTuple`, and `ParamSpec` from `typing`.

## BAD

```python
from typing import Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

class Stack(Generic[T]):
    def push(self, item: T) -> None: ...
    def pop(self) -> T: ...

MyList = list[T]  # not a proper type alias
```

## GOOD

```python
class Stack[T]:
    def push(self, item: T) -> None: ...
    def pop(self) -> T: ...

type MyList[T] = list[T]

def first[T](items: list[T]) -> T:
    return items[0]
```

## Why

- No boilerplate `TypeVar("T")` declarations
- Scope is explicit — type params are local to their class/function/alias
- `type` statement creates proper type aliases with lazy evaluation
- Cleaner syntax for bounded types: `class Num[T: (int, float)]`

## Version Notes

- 3.12+: `class C[T]`, `def f[T]()`, `type Alias[T] = ...`
- Pre-3.12: Must use `TypeVar`, `Generic`, and `TypeAlias`

## References

- [PEP 695 — Type Parameter Syntax](https://peps.python.org/pep-0695/)
