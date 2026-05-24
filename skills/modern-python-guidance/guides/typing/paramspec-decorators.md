---
id: paramspec-decorators
title: Use ParamSpec for Typed Decorators
category: typing
layer: 1
tags:
  - type-hints
  - decorators
  - paramspec
aliases:
  - ParamSpec
  - typing.ParamSpec
  - Callable
python: ">=3.10"
frequency: medium
pep: 612
---

# Use ParamSpec for Typed Decorators

Since Python 3.10, use `ParamSpec` to preserve the parameter types of decorated functions. Without it, decorators erase all type information.

## BAD

```python
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

def retry(func: F) -> F:  # loses parameter info in practice
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for _ in range(3):
            try:
                return func(*args, **kwargs)
            except Exception:
                pass
        return func(*args, **kwargs)
    return wrapper  # type: ignore
```

## GOOD

```python
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def retry(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for _ in range(3):
            try:
                return func(*args, **kwargs)
            except Exception:
                pass
        return func(*args, **kwargs)
    return wrapper

# 3.12+ with PEP 695:
# def retry[**P, R](func: Callable[P, R]) -> Callable[P, R]: ...
```

## Why

- Preserves full parameter types through decoration
- Type checkers can verify argument types at call sites
- No more `# type: ignore` on decorator return
- `P.args` and `P.kwargs` capture positional and keyword args separately

## Version Notes

- 3.10+: `from typing import ParamSpec`
- 3.12+: `def retry[**P, R](func): ...` syntax (PEP 695)
- Pre-3.10: `from typing_extensions import ParamSpec`

## References

- [PEP 612 — Parameter Specification Variables](https://peps.python.org/pep-0612/)
