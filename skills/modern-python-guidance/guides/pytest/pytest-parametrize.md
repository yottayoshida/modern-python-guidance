---
id: pytest-parametrize
title: Use pytest.mark.parametrize Instead of Test Loops
category: pytest
layer: 2
tags:
  - pytest
  - testing
  - parametrize
aliases:
  - parameterize
  - test-loop
python: ">=3.9"
frequency: high
---

# Use pytest.mark.parametrize

Use `@pytest.mark.parametrize` to run a test with multiple inputs instead of writing loops inside test functions or duplicating test functions.

## BAD

```python
def test_validate_email():
    valid_emails = ["user@example.com", "a@b.co", "user+tag@domain.org"]
    for email in valid_emails:
        assert validate_email(email) is True

    invalid_emails = ["", "not-an-email", "@domain.com", "user@"]
    for email in invalid_emails:
        assert validate_email(email) is False
```

## GOOD

```python
import pytest

@pytest.mark.parametrize("email", [
    "user@example.com",
    "a@b.co",
    "user+tag@domain.org",
])
def test_validate_email_valid(email):
    assert validate_email(email) is True

@pytest.mark.parametrize("email", [
    "",
    "not-an-email",
    "@domain.com",
    "user@",
])
def test_validate_email_invalid(email):
    assert validate_email(email) is False
```

## Why

- Each parameter set runs as a separate test -- failure in one case does not skip the rest
- Test output shows exactly which input failed: `test_validate_email_valid[a@b.co] FAILED`
- Easy to add new test cases without modifying test logic
- Ruff PT001-003 check parametrize decorator style, but mpg pre-generation guidance ensures the parametrize pattern is used from the start instead of writing loops

## Version Notes

- Available since pytest 2.0. Works on all supported Python versions
- Use `pytest.param(..., id="descriptive-name")` for readable test IDs

## References

- [pytest Parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [pytest.param](https://docs.pytest.org/en/stable/reference/reference.html#pytest-param)
