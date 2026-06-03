---
id: override-decorator
title: Use @override to Mark Method Overrides
category: typing
layer: 1
tags:
  - type-hints
  - inheritance
  - override
aliases:
  - typing.override
python: ">=3.12"
frequency: medium
pep: 698
detect-patterns:
---

# Use @override to Mark Method Overrides

Since Python 3.12, use `@override` from `typing` to explicitly mark methods that override a parent class method. Type checkers will flag errors if the parent method doesn't exist.

## BAD

```python
class Animal:
    def speak(self) -> str:
        return ""

class Dog(Animal):
    def spek(self) -> str:  # typo goes unnoticed
        return "woof"
```

## GOOD

```python
from typing import override

class Animal:
    def speak(self) -> str:
        return ""

class Dog(Animal):
    @override
    def speak(self) -> str:
        return "woof"

    @override
    def spek(self) -> str:  # type checker flags: no parent method 'spek'
        return "woof"
```

## Why

- Catches typos and missing parent methods at type-check time
- Documents intent — clearly shows which methods are overrides
- Prevents silent breakage when parent class renames a method

## Version Notes

- 3.12+: `from typing import override`
- 3.11 and below: `from typing_extensions import override`

## References

- [PEP 698 — Override Decorator for Static Typing](https://peps.python.org/pep-0698/)
