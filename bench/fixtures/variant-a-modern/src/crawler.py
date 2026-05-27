import asyncio

import httpx


async def crawl(urls: list[str]) -> list[str]:
    results = []
    async with httpx.AsyncClient() as client:
        async with asyncio.TaskGroup() as tg:
            for url in urls:
                tg.create_task(_fetch(client, url, results))
    return results


async def _fetch(client: httpx.AsyncClient, url: str, results: list[str]) -> None:
    async with asyncio.timeout(30):
        response = await client.get(url)
        results.append(response.text)


async def download_large(client: httpx.AsyncClient, url: str, dest: str) -> None:
    async with client.stream("GET", url) as resp:
        async for chunk in resp.aiter_bytes():
            pass
