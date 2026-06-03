---
id: exception-groups
title: Use except* for Exception Groups
category: async
layer: 1
tags:
  - asyncio
  - exceptions
  - error-handling
aliases:
  - ExceptionGroup
  - except*
  - BaseExceptionGroup
python: ">=3.11"
frequency: medium
pep: 654
detect-patterns:
---

# Use except* for Exception Groups

Since Python 3.11, use `except*` to handle multiple concurrent exceptions from `TaskGroup` and other async contexts.

## BAD

```python
import asyncio

async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fetch_users())
            tg.create_task(fetch_orders())
    except Exception as e:
        # Only sees the ExceptionGroup wrapper, not individual errors
        print(f"Something failed: {e}")
```

## GOOD

```python
import asyncio

async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fetch_users())
            tg.create_task(fetch_orders())
    except* ValueError as eg:
        for e in eg.exceptions:
            print(f"Validation error: {e}")
    except* ConnectionError as eg:
        for e in eg.exceptions:
            print(f"Connection failed: {e}")
```

## Why

- `TaskGroup` raises `ExceptionGroup` when multiple tasks fail simultaneously
- `except*` matches and extracts specific exception types from the group
- Multiple `except*` clauses can each handle different types from the same group
- Traditional `except` sees only the `ExceptionGroup` wrapper

## Version Notes

- 3.11+: `except*`, `ExceptionGroup`, `BaseExceptionGroup`
- Pre-3.11: Use `exceptiongroup` backport package

## References

- [PEP 654 — Exception Groups and except*](https://peps.python.org/pep-0654/)
