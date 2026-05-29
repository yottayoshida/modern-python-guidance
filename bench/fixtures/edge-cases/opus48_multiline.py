"""Opus 4.8 style: verbose, multi-line, heavily documented code.

This fixture reproduces the patterns that broke the V4 grep scorer.
Every function here is MODERN but would false-flag under grep-based detection.
"""
import asyncio
import subprocess
from pathlib import Path
from typing import TypeGuard


def run_command(cmd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a subprocess safely from a list of arguments.

    Passing a list (not a shell string) avoids shell injection: the program name
    and each argument are kept distinct and never re-parsed by a shell.
    Never use shell=True on untrusted input.
    """

    return subprocess.run(
        [cmd, *args],
        check=True,
        capture_output=True,
        text=True,
    )


async def scan_directory(root: str | Path) -> list[Path]:
    """Walk root recursively, batch files, process concurrently.

    Uses TaskGroup for structured concurrency. A failure in one batch
    is recorded while the other batches still complete.
    """

    root_path = Path(root)
    files = [p for p in root_path.rglob("*") if p.is_file()]
    batches = [files[i : i + 10] for i in range(0, len(files), 10)]

    errors: list[str] = []
    results: list[Path] = []

    async with asyncio.TaskGroup() as tg:
        for batch in batches:
            tg.create_task(_process_batch(batch, results, errors))

    return results


async def _process_batch(
    batch: list[Path],
    results: list[Path],
    errors: list[str],
) -> None:
    try:
        for path in batch:
            results.append(path)
    except OSError as exc:
        errors.append(str(exc))


def is_positive_int(val: object) -> TypeGuard[int]:
    """Narrow val to int when it is a positive integer.

    bool is a subclass of int in Python, so it is explicitly excluded.
    After if is_positive_int(x): a type checker treats x as int.
    """

    return isinstance(val, int) and not isinstance(val, bool) and val > 0
