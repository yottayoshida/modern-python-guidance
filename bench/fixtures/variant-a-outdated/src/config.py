import os.path
import toml
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AppConfig:
    db_url: str
    debug: bool = False
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


def load_config(path: str) -> dict:
    config_path = os.path.join(os.path.dirname(__file__), path)
    if os.path.exists(config_path):
        with open(config_path) as f:
            return toml.load(f)
    return {}
