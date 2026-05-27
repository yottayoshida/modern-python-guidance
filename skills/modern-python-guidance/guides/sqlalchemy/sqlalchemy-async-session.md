---
id: sqlalchemy-async-session
title: Use AsyncSession for Async Database Access
category: sqlalchemy
layer: 2
tags:
  - sqlalchemy
  - async
  - asyncio
  - session
aliases:
  - async-engine
  - async-sessionmaker
python: ">=3.9"
frequency: medium
---

# Use AsyncSession for Async Database Access

Use `AsyncSession` with `create_async_engine` instead of wrapping synchronous sessions with `sync_to_async` or `run_in_executor`.

## BAD

```python
import asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

engine = create_engine("postgresql://user:pass@localhost/db")

async def get_user(user_id: int):
    def _query():
        with Session(engine) as session:
            return session.get(User, user_id)
    return await asyncio.to_thread(_query)
```

## GOOD

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
async_session = async_sessionmaker(engine, class_=AsyncSession)

async def get_user(user_id: int):
    async with async_session() as session:
        return await session.get(User, user_id)
```

## Why

- Native async avoids thread-pool overhead from `asyncio.to_thread`
- Connection pool is managed by the async engine natively
- `async with` ensures proper session cleanup on exceptions
- Consistent async/await chain without sync-to-async bridges

## Version Notes

- SQLAlchemy 1.4+ (alpha async support), 2.0+ (stable)
- Requires an async DB driver: `asyncpg` (PostgreSQL), `aiosqlite` (SQLite), `aiomysql` (MySQL)
- Sync `Session` remains appropriate for synchronous applications

## References

- [SQLAlchemy AsyncIO Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Async Session API](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession)
