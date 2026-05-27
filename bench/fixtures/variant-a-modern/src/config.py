import tomllib
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, UTC


@dataclass(slots=True)
class AppConfig:
    db_url: str
    debug: bool = False
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
