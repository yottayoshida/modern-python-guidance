---
id: httpx-async-client-reuse
title: Reuse httpx.AsyncClient Instead of Creating Per-Request
category: httpx
layer: 2
tags:
  - httpx
  - async
  - connection-pooling
aliases:
  - httpx
  - AsyncClient
  - aiohttp
  - requests
python: ">=3.9"
frequency: high
---

# Reuse httpx.AsyncClient

Create one `httpx.AsyncClient` and reuse it across requests instead of creating a new client per call.

## BAD

```python
import httpx

async def fetch_user(user_id: int) -> dict:
    response = httpx.get(f"https://api.example.com/users/{user_id}")
    return response.json()

async def fetch_many(ids: list[int]) -> list[dict]:
    return [await fetch_user(i) for i in ids]
```

## GOOD

```python
import httpx

async def fetch_many(ids: list[int]) -> list[dict]:
    async with httpx.AsyncClient(base_url="https://api.example.com") as client:
        results = []
        for user_id in ids:
            resp = await client.get(f"/users/{user_id}")
            resp.raise_for_status()
            results.append(resp.json())
        return results
```

## Why

- Per-request clients skip connection pooling — each call opens a new TCP+TLS handshake
- `AsyncClient` maintains a connection pool, reusing connections across requests
- `httpx` is the modern replacement for `requests` (sync) and `aiohttp` (async)
- Context manager ensures connections are properly closed
- `base_url` eliminates URL duplication

## Version Notes

- `httpx` is a third-party package, not stdlib
- Works on Python 3.9+ with `httpx >= 0.23`
- Preferred over `requests` for new async code
- Preferred over `aiohttp` for simpler API and `requests`-like interface

## References

- [httpx Async Client](https://www.python-httpx.org/async/)
- [httpx Connection Pooling](https://www.python-httpx.org/advanced/clients/)
