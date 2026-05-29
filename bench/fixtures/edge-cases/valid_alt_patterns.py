"""Valid alternative patterns that should score VALID_ALT, not OUTDATED.

SA2: sync SQLAlchemy 2.0 (create_engine + select() style)
TY6: TypeGuard (broader semantics than TypeIs, still valid)
AS3: TaskGroup + per-task try/except (structured concurrency without except*)
"""
import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from typing import TypeGuard


# SA2: sync SQLAlchemy 2.0 — VALID_ALT
engine = create_engine("sqlite:///test.db")


def get_users():
    with Session(engine) as session:
        return session.scalars(select(User)).all()


# TY6: TypeGuard — VALID_ALT
def is_str_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)


# AS3: TaskGroup + per-task try/except — VALID_ALT
async def fetch_all(urls: list[str]) -> list[str]:
    results: list[str] = []
    async with asyncio.TaskGroup() as tg:
        for url in urls:
            tg.create_task(_safe_fetch(url, results))
    return results


async def _safe_fetch(url: str, results: list[str]) -> None:
    try:
        results.append(f"fetched: {url}")
    except Exception:
        pass
