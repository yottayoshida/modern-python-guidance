---
id: removeprefix-removesuffix
title: Use str.removeprefix/removesuffix Instead of Slicing
category: stdlib
layer: 1
tags:
  - string
  - stdlib
aliases:
  - removeprefix
  - removesuffix
  - lstrip
  - rstrip
python: ">=3.9"
frequency: medium
pep: 616
detect-patterns:
---

# Use str.removeprefix/removesuffix

Since Python 3.9, use `str.removeprefix()` and `str.removesuffix()` instead of manual slicing or `lstrip()`/`rstrip()`.

## BAD

```python
filename = "test_utils.py"

# Manual slicing — must know exact length
if filename.startswith("test_"):
    name = filename[5:]  # fragile: magic number 5

# Common mistake: lstrip removes CHARACTERS, not prefix
name = filename.lstrip("test_")  # removes t, e, s, _, not "test_"
# "test_utils.py".lstrip("test_") == "utils.py" (lucky)
# "test_test.py".lstrip("test_") == ".py" (wrong!)
```

## GOOD

```python
filename = "test_utils.py"

name = filename.removeprefix("test_")  # "utils.py"
base = filename.removesuffix(".py")     # "test_utils"

# Safe: returns original string if prefix/suffix not found
name = "production.py".removeprefix("test_")  # "production.py"
```

## Why

- No magic numbers or `len()` calculations
- Semantically clear — removes a specific string, not individual characters
- Safe — returns the original string unchanged if prefix/suffix not present
- Avoids the `lstrip`/`rstrip` character-set trap

## Version Notes

- 3.9+: `str.removeprefix()`, `str.removesuffix()`
- Also available on `bytes` and `bytearray`

## References

- [PEP 616 — String methods to remove prefixes and suffixes](https://peps.python.org/pep-0616/)
