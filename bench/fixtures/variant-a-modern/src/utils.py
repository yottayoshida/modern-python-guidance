import subprocess
from typing import ParamSpec, TypeIs

P = ParamSpec("P")


def merge_defaults(user: dict, defaults: dict) -> dict:
    return defaults | user


def run_command(cmd: str, *extra: str) -> str:
    result = subprocess.run([cmd, *extra], capture_output=True, text=True, check=True)
    return result.stdout


def is_positive_int(val: object) -> TypeIs[int]:
    return isinstance(val, int) and val > 0
