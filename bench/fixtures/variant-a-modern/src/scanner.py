import asyncio
from enum import Enum
from pathlib import Path


class FileCategory(Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    OTHER = "other"


def categorize(ext: str) -> FileCategory:
    match ext:
        case ".jpg" | ".png" | ".gif":
            return FileCategory.IMAGE
        case ".mp4" | ".avi":
            return FileCategory.VIDEO
        case ".pdf" | ".docx":
            return FileCategory.DOCUMENT
        case _:
            return FileCategory.OTHER


def parse_log_line(line: str) -> str:
    return line.removeprefix("[INFO] ").removesuffix("\n")


async def safe_scan(paths: list[Path]) -> list[FileCategory]:
    results = []
    try:
        async with asyncio.TaskGroup() as tg:
            for p in paths:
                tg.create_task(_scan_one(p, results))
    except* OSError as eg:
        for exc in eg.exceptions:
            print(f"OS error: {exc}")
    return results


async def _scan_one(p: Path, results: list[FileCategory]) -> None:
    results.append(categorize(p.suffix))
