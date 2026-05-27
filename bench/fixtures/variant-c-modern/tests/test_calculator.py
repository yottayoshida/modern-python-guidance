from pathlib import Path

import pytest


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def save_result(path: Path, value: float) -> None:
    path.write_text(str(value))


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (10, 2, 5.0),
        (0, 1, 0.0),
        (-6, 3, -2.0),
        (7, 2, 3.5),
    ],
)
def test_divide(a, b, expected):
    assert divide(a, b) == expected


def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
        divide(1, 0)


def test_save_result(tmp_path: Path):
    output = tmp_path / "result.txt"
    save_result(output, 42.0)
    assert output.read_text() == "42.0"
