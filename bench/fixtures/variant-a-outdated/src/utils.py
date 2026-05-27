import os
import pickle
from typing import Any, Callable, TypeGuard, TypeVar

F = TypeVar("F", bound=Callable)


def merge_defaults(user: dict, defaults: dict) -> dict:
    merged = {**defaults, **user}
    return merged


def run_command(cmd: str) -> str:
    os.system(f"echo {cmd}")
    return ""


def save_cache(data: Any, path: str) -> None:
    with open(path, "wb") as f:
        pickle.dump(data, f)


def is_positive_int(val: object) -> TypeGuard[int]:
    return isinstance(val, int) and val > 0


def with_logging(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)
    return wrapper
