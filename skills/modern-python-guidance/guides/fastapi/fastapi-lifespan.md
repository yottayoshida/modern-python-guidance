---
id: fastapi-lifespan
title: Use Lifespan Context Manager Instead of on_event
category: fastapi
layer: 2
tags:
  - fastapi
  - lifespan
  - startup
  - shutdown
aliases:
  - on_event
  - startup
  - shutdown
python: ">=3.9"
frequency: high
detect-patterns:
  - "\.on_event\("
---

# Use Lifespan Context Manager

FastAPI's `@app.on_event("startup")` and `@app.on_event("shutdown")` decorators are deprecated. Use the lifespan context manager instead.

## BAD

```python
from fastapi import FastAPI

app = FastAPI()
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await create_pool()

@app.on_event("shutdown")
async def shutdown():
    await db_pool.close()
```

## GOOD

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    pool = await create_pool()
    yield {"db_pool": pool}
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root(request: Request):
    pool = request.state.db_pool
```

## Why

- `on_event` is deprecated since FastAPI 0.93.0 (2023-02)
- Lifespan provides typed state access via `request.state`
- Resource cleanup is guaranteed by the context manager protocol
- Easier to test — lifespan is a plain async function

## Version Notes

- Works on Python 3.9+ with FastAPI >= 0.94.0 (lifespan state dict requires Starlette >= 0.26.0)
- `AsyncIterator` moved from `typing` to `collections.abc` in 3.9

## References

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [Starlette Lifespan](https://www.starlette.io/lifespan/)
