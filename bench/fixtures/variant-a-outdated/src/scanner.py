import asyncio
from enum import Enum


class FileCategory(Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    OTHER = "other"


def categorize(ext: object) -> FileCategory:
    if isinstance(ext, str) and ext in (".jpg", ".png", ".gif"): return FileCategory.IMAGE  # noqa
    elif isinstance(ext, str) and ext in (".mp4", ".avi"): return FileCategory.VIDEO  # noqa
    elif isinstance(ext, str) and ext in (".pdf", ".docx"): return FileCategory.DOCUMENT  # noqa
    else: return FileCategory.OTHER  # noqa


def parse_log_line(line: str) -> str:
    prefix = "[INFO] "
    if line.startswith(prefix):
        return line[len(prefix):].rstrip("\n")
    return line.rstrip("\n")


async def safe_scan(paths):
    results = []
    try:
        tasks = [_scan_one(p) for p in paths]
        results = await asyncio.gather(*tasks)
    except Exception as e:
        print(f"Error: {e}")
    return results


async def _scan_one(p):
    return categorize(p.suffix)
