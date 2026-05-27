import asyncio
from typing import List

import httpx


async def crawl(urls: List[str]) -> List[str]:
    results = []
    tasks = [_fetch(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, str)]


async def _fetch(url: str) -> str:
    try:
        result = await asyncio.wait_for(_do_fetch(url), timeout=30)
        return result
    except asyncio.TimeoutError:
        return ""


async def _do_fetch(url: str) -> str:
    response = httpx.get(url)
    return response.text


async def batch_crawl(urls: List[str]) -> List[str]:
    try:
        tasks = [_do_fetch(url) for url in urls]
        results = await asyncio.gather(*tasks)
    except ExceptionGroup as eg:
        for exc in eg.exceptions:
            if isinstance(exc, Exception):
                print(f"Error: {exc}")
        results = []
    return [r for r in results if isinstance(r, str)]
