---
id: dataclass-modern
title: Use Modern Dataclass Features (slots, kw_only)
category: data-structures
layer: 1
tags:
  - dataclass
  - slots
  - kw_only
aliases:
  - dataclass
  - dataclasses
python: ">=3.10"
frequency: medium
---

# Use Modern Dataclass Features

Since Python 3.10, dataclasses support `slots=True` and `kw_only=True` for better performance and safer APIs.

## BAD

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0

# No slots: allows typos on attributes
p = Point(1.0, 2.0)
p.w = 3.0  # silently creates new attribute (typo for 'z')

# Positional args: easy to mix up x and y
p = Point(2.0, 1.0)  # is this (x=2, y=1) or (x=1, y=2)?
```

## GOOD

```python
from dataclasses import dataclass

@dataclass(slots=True, kw_only=True)
class Point:
    x: float
    y: float
    z: float = 0.0

p = Point(x=1.0, y=2.0)
p.w = 3.0  # AttributeError: 'Point' has no attribute 'w'

# kw_only forces explicit names — no positional confusion
p = Point(x=2.0, y=1.0)  # intent is clear
```

## Why

- `slots=True`: 20-35% less memory, faster attribute access, prevents typo attributes
- `kw_only=True`: forces named arguments, eliminates positional ordering bugs
- `frozen=True` + `slots=True`: fast immutable value objects
- Combine for production data classes: `@dataclass(slots=True, frozen=True, kw_only=True)`

## Version Notes

- 3.10+: `slots=True`, `kw_only=True`
- 3.10+: Per-field `kw_only` via `field(kw_only=True)`
- 3.7-3.9: Basic `@dataclass` without slots/kw_only

## References

- [dataclasses documentation](https://docs.python.org/3/library/dataclasses.html)
