import pytest


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def save_result(path, value: float) -> None:
    with open(str(path), "w") as f:
        f.write(str(value))


def test_divide_positive():
    assert divide(10, 2) == 5.0


def test_divide_zero_numerator():
    assert divide(0, 1) == 0.0


def test_divide_negative():
    assert divide(-6, 3) == -2.0


def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)


def test_save_result(tmpdir):
    output = tmpdir.join("result.txt")
    save_result(str(output), 42.0)
    assert output.read() == "42.0"
