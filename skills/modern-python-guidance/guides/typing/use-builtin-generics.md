---
id: use-builtin-generics
title: Use Built-in Generic Types Instead of typing Module
category: typing
layer: 1
tags:
  - type-hints
  - generics
  - typing
aliases:
  - typing.List
  - typing.Dict
  - typing.Optional
  - typing.Tuple
  - typing.Set
python: ">=3.9"
frequency: high
pep: 585
detect-patterns:
  - "from typing import .*\b(List|Dict|Set|Tuple|FrozenSet|Type|Deque|DefaultDict|OrderedDict|Counter|ChainMap)\b"
---

# Use Built-in Generic Types

Since Python 3.9, built-in types support subscript syntax directly. The `typing` module aliases are deprecated.

## BAD

```python
from typing import Dict, List, Optional, Set, Tuple

def process(items: List[str]) -> Dict[str, int]:
    seen: Set[str] = set()
    pair: Tuple[str, int] = ("a", 1)
    name: Optional[str] = None
    return {}
```

## GOOD

```python
def process(items: list[str]) -> dict[str, int]:
    seen: set[str] = set()
    pair: tuple[str, int] = ("a", 1)
    name: str | None = None
    return {}
```

## Why

- Fewer imports, cleaner code
- Same runtime types used in annotations
- `typing` aliases deprecated since 3.9, scheduled for removal in 3.14+

## Version Notes

- 3.9+: `list[str]`, `dict[str, int]`, `tuple[str, int]`, `set[str]`
- 3.10+: `str | None` replaces `Optional[str]` (PEP 604)

## References

- [PEP 585 — Type Hinting Generics In Standard Collections](https://peps.python.org/pep-0585/)
- [PEP 604 — Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
