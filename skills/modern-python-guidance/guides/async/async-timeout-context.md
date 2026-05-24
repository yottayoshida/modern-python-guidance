---
id: async-timeout-context
title: Use asyncio.timeout Instead of wait_for
category: async
layer: 1
tags:
  - asyncio
  - timeout
aliases:
  - asyncio.wait_for
  - asyncio.timeout
python: ">=3.11"
frequency: medium
---

# Use asyncio.timeout Instead of wait_for

Since Python 3.11, use the `asyncio.timeout` context manager instead of `asyncio.wait_for`. It provides structured cancellation and works with any block of async code.

## BAD

```python
import asyncio

async def fetch_data():
    try:
        result = await asyncio.wait_for(slow_operation(), timeout=5.0)
    except asyncio.TimeoutError:
        result = default_value

    # wait_for only wraps a single awaitable
    # Cannot timeout multiple operations together
```

## GOOD

```python
import asyncio

async def fetch_data():
    try:
        async with asyncio.timeout(5.0):
            data = await slow_operation()
            parsed = await parse(data)
            # Both operations share the 5s budget
    except TimeoutError:
        return default_value
```

## Why

- Context manager scopes timeout to an entire block, not just one awaitable
- Multiple operations share the same deadline
- Raises standard `TimeoutError` (not `asyncio.TimeoutError`)
- `asyncio.timeout(None)` disables timeout (useful for conditional timeouts)

## Version Notes

- 3.11+: `asyncio.timeout(delay)` and `asyncio.timeout_at(when)`
- 3.12+: `asyncio.timeout` raises `TimeoutError` (not `asyncio.TimeoutError`)
- Pre-3.11: Use `async-timeout` package

## References

- [asyncio.timeout documentation](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout)
