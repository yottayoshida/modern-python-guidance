---
id: fastapi-typed-state
title: Use TypedDict or dataclass for App State
category: fastapi
layer: 2
tags:
  - fastapi
  - state
  - typed
aliases:
  - app.state
  - request.state
  - typed state
python: ">=3.9"
frequency: medium
---

# Use TypedDict or dataclass for App State

Instead of untyped `app.state.foo` attribute access, use a typed state dict via the lifespan pattern.

## BAD

```python
from fastapi import FastAPI, Request

app = FastAPI()
app.state.db_pool = create_pool()
app.state.cache = create_cache()

@app.get("/")
async def root(request: Request):
    pool = request.state.db_pool  # Any — no type checking
    cache = request.state.cche   # typo silently passes
```

## GOOD

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request

@dataclass(slots=True)
class AppState:
    db_pool: Pool
    cache: Cache

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    pool = await create_pool()
    cache = await create_cache()
    yield {"db_pool": pool, "cache": cache}
    await cache.close()
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root(request: Request):
    pool = request.state.db_pool  # accessible via lifespan state
```

## Why

- `app.state` is untyped — typos and missing attributes are invisible to type checkers
- Lifespan state dict makes initialization and cleanup explicit
- `dataclass` or `TypedDict` documents the expected shape
- Resource cleanup is guaranteed by the context manager

## Version Notes

- Lifespan state dict requires FastAPI >= 0.94.0 (Starlette >= 0.26.0)
- `@dataclass(slots=True)` requires Python 3.10+; use plain `@dataclass` on 3.9

## References

- [FastAPI Lifespan State](https://fastapi.tiangolo.com/advanced/events/#lifespan-state)
- [Starlette State](https://www.starlette.io/lifespan/)
