---
id: pytest-raises-match
title: Use pytest.raises with match Parameter
category: pytest
layer: 2
tags:
  - pytest
  - testing
  - exceptions
  - raises
aliases:
  - bare-raises
  - exception-match
python: ">=3.9"
frequency: medium
---

# Use pytest.raises with match

Always pass a `match` pattern to `pytest.raises()` to verify the exception message, not just the exception type.

## BAD

```python
import pytest

def test_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        calculate(10, 0)

def test_invalid_input():
    with pytest.raises(ValueError):
        parse_config("not-valid")
```

## GOOD

```python
import pytest

def test_division_by_zero():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        calculate(10, 0)

def test_invalid_input():
    with pytest.raises(ValueError, match=r"invalid config format: .+"):
        parse_config("not-valid")
```

## Why

- Bare `pytest.raises(ValueError)` passes for any `ValueError` -- it may catch a different error than intended, creating a false-positive test
- `match` takes a regex pattern checked against `str(exception)` -- it verifies the right error was raised
- Ruff PT011 checks this for 7 broad exception types (`BaseException`, `Exception`, `ValueError`, `OSError`, `IOError`, `EnvironmentError`, `socket.error`). mpg pre-generation guidance covers all exception types from the start, making Ruff post-checks unnecessary

## Version Notes

- `match` parameter available since pytest 2.8.0
- `match` uses `re.search` semantics (matches anywhere in the string)

## References

- [pytest.raises](https://docs.pytest.org/en/stable/reference/reference.html#pytest-raises)
- [Ruff PT011](https://docs.astral.sh/ruff/rules/pytest-raises-too-broad/)
