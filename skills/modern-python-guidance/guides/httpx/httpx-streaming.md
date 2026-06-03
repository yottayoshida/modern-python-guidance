---
id: httpx-streaming
title: Use httpx Streaming for Large Responses
category: httpx
layer: 2
tags:
  - httpx
  - streaming
  - memory
aliases:
  - streaming
  - stream
  - large response
python: ">=3.9"
frequency: medium
detect-patterns:
---

# Use httpx Streaming for Large Responses

Use `client.stream()` instead of `client.get()` for large responses to avoid loading the entire body into memory.

## BAD

```python
import httpx

async def download_file(url: str, path: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        with open(path, "wb") as f:
            f.write(response.content)  # entire file in memory
```

## GOOD

```python
import httpx

async def download_file(url: str, path: str) -> None:
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
```

## Why

- `response.content` loads the entire response body into memory at once
- `client.stream()` reads the response incrementally — constant memory usage
- Essential for large file downloads, SSE streams, and NDJSON feeds
- `aiter_bytes()`, `aiter_lines()`, `aiter_text()` provide different iteration modes

## Streaming Iteration Methods

| Method | Use case |
|--------|---------|
| `aiter_bytes(chunk_size)` | Binary downloads, file writes |
| `aiter_lines()` | Line-delimited text (NDJSON, logs) |
| `aiter_text()` | Streamed text with encoding handling |
| `aiter_raw()` | Raw bytes without decompression |

## References

- [httpx Streaming Responses](https://www.python-httpx.org/async/#streaming-responses)
