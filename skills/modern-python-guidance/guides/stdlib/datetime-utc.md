---
id: datetime-utc
title: Use datetime.now(UTC) Instead of utcnow()
category: stdlib
layer: 1
tags:
  - datetime
  - timezone
  - utc
aliases:
  - utcnow
  - datetime.utcnow
  - datetime.utcfromtimestamp
python: ">=3.11"
frequency: high
---

# Use datetime.now(UTC) Instead of utcnow()

`datetime.utcnow()` returns a naive datetime (no timezone info). This is a common source of bugs. Use `datetime.now(UTC)` for timezone-aware UTC datetimes.

## BAD

```python
from datetime import datetime

now = datetime.utcnow()
ts = datetime.utcfromtimestamp(1234567890)
```

## GOOD

```python
from datetime import UTC, datetime

now = datetime.now(UTC)
ts = datetime.fromtimestamp(1234567890, tz=UTC)
```

## Why

- `utcnow()` and `utcfromtimestamp()` are deprecated since Python 3.12
- Naive datetimes cause subtle bugs in timezone arithmetic
- `datetime.now(UTC)` returns a proper timezone-aware datetime
- The `UTC` singleton was added in Python 3.11

## Version Notes

- 3.11+: `datetime.UTC` constant available
- 3.12+: `utcnow()` and `utcfromtimestamp()` emit `DeprecationWarning`
- For 3.9-3.10: use `datetime.now(timezone.utc)` instead

## References

- [datetime.UTC docs](https://docs.python.org/3/library/datetime.html#datetime.UTC)
- [What's New in Python 3.12 — Deprecations](https://docs.python.org/3/whatsnew/3.12.html)
