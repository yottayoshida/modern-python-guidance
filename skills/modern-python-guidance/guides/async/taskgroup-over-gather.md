---
id: taskgroup-over-gather
title: Use asyncio.TaskGroup Instead of asyncio.gather
category: async
layer: 1
tags:
  - asyncio
  - concurrency
  - taskgroup
aliases:
  - asyncio.gather
  - gather
python: ">=3.11"
frequency: high
detect-patterns:
  - "asyncio\.gather\("
---

# Use asyncio.TaskGroup Instead of asyncio.gather

`asyncio.TaskGroup` provides structured concurrency with proper error handling. `asyncio.gather` silently drops errors from other tasks when one fails.

## BAD

```python
import asyncio

async def main():
    results = await asyncio.gather(
        fetch_users(),
        fetch_orders(),
        fetch_products(),
    )
```

## GOOD

```python
import asyncio

async def main():
    async with asyncio.TaskGroup() as tg:
        users_task = tg.create_task(fetch_users())
        orders_task = tg.create_task(fetch_orders())
        products_task = tg.create_task(fetch_products())

    results = (users_task.result(), orders_task.result(), products_task.result())
```

## Why

- `gather` with `return_exceptions=False` cancels remaining tasks on first error but may swallow secondary exceptions
- `TaskGroup` raises `ExceptionGroup` containing all failures
- Structured concurrency: all tasks are guaranteed to finish before the block exits
- Clearer intent — each task is named and individually accessible

## Version Notes

- 3.11+: `asyncio.TaskGroup` added
- For 3.10 and below, consider `anyio.create_task_group()` as a backport

## References

- [PEP 654 — Exception Groups](https://peps.python.org/pep-0654/)
- [asyncio.TaskGroup docs](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup)
