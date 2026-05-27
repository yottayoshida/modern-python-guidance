---
id: dataclass-modern
title: Use Modern Dataclass Features (frozen, slots, kw_only)
category: data-structures
layer: 1
tags:
  - dataclass
  - slots
  - kw_only
  - frozen
  - immutable
aliases:
  - dataclass
  - dataclasses
python: ">=3.10"
frequency: high
---

# Use Modern Dataclass Features

Since Python 3.10, dataclasses support `frozen=True`, `slots=True`, and `kw_only=True` for immutable value objects with better performance.

## BAD

```python
from dataclasses import dataclass

@dataclass
class AppConfig:
    db_host: str
    db_port: int
    debug: bool = False

config = AppConfig("localhost", 5432)
config.db_host = "evil.example.com"  # mutable — accidental or malicious mutation
config.typo_field = True  # silently creates new attribute
```

## GOOD

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True, kw_only=True)
class AppConfig:
    db_host: str
    db_port: int
    debug: bool = False

config = AppConfig(db_host="localhost", db_port=5432)
config.db_host = "evil"  # FrozenInstanceError
config.typo_field = True  # AttributeError
```

## Why

### When to use each flag

| Flag | Use when | Effect |
|------|----------|--------|
| `frozen=True` | Value objects, configs, DTOs, dict keys | Immutable + hashable |
| `slots=True` | Always (unless you need `__dict__`) | 20-35% less memory, faster access, blocks typo attrs |
| `kw_only=True` | 3+ fields, or fields of same type | Forces named args, prevents ordering bugs |

### When NOT to use

- **`frozen`**: Skip when you need mutable builder pattern or in-place updates in tight loops
- **`slots`**: Skip when you need `__dict__` introspection, multiple inheritance with conflicting slots, or dynamic attribute assignment
- **`kw_only`**: Skip for 1-2 field classes where positional is unambiguous (e.g., `Point(x, y)`)

### Decision checklist

1. Is this a value object, config, or DTO? → Add `frozen=True`
2. Do you need `__dict__` or multiple inheritance? → If no, add `slots=True`
3. Are there 3+ fields or fields of the same type? → Add `kw_only=True`

## Version Notes

- 3.10+: `slots=True`, `kw_only=True`
- 3.10+: Per-field `kw_only` via `field(kw_only=True)`
- 3.7-3.9: Basic `@dataclass` and `frozen=True` only (no slots/kw_only)

## References

- [dataclasses documentation](https://docs.python.org/3/library/dataclasses.html)
