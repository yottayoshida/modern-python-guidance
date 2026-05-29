---
id: deferred-annotations
title: 'Drop "from __future__ import annotations" on Python 3.14+'
category: typing
layer: 1
tags:
  - type-hints
  - annotations
  - forward-reference
aliases:
  - "from __future__ import annotations"
  - "__future__.annotations"
  - ForwardRef
python: ">=3.14"
frequency: high
pep: 649
---

# Drop `from __future__ import annotations` on Python 3.14+

On Python 3.14+, annotations are lazily evaluated by default (PEP 649). The `from __future__ import annotations` import is no longer needed for forward references in 3.14-only projects.

## BAD

```python
from __future__ import annotations

class Tree:
    left: Tree | None = None
    right: Tree | None = None

    def children(self) -> list[Tree]:
        return [c for c in (self.left, self.right) if c]
```

## GOOD

```python
class Tree:
    left: Tree | None = None
    right: Tree | None = None

    def children(self) -> list[Tree]:
        return [c for c in (self.left, self.right) if c]
```

## Why

- Python 3.14 evaluates annotations lazily by default, so forward references like `Tree` inside the `Tree` class body just work
- The future import forces all-string semantics (PEP 563), which is different from 3.14's lazy evaluation and can interact poorly with runtime annotation consumers
- Removing the unnecessary import keeps the module cleaner and avoids the subtle behavioral difference between stringified and lazily-evaluated annotations

## Version Notes

- 3.14+: Annotations are lazily evaluated by default. Remove `from __future__ import annotations` in 3.14-only projects
- Pre-3.14: The future import remains the correct way to enable string annotations for forward references
- `from __future__ import annotations` is deprecated but NOT removed in 3.14. It still works but forces all-string semantics. Removal is not expected before Python 3.13 EOL (~2029)
- Libraries that read annotations at runtime (`typing.get_type_hints()`, Pydantic, FastAPI, attrs) may need updates for 3.14's lazy evaluation. Verify library compatibility before removing the import in projects that depend on runtime annotation inspection

## References

- [PEP 649 -- Deferred Evaluation of Annotations Using Descriptors](https://peps.python.org/pep-0649/)
- [PEP 749 -- Implementing PEP 649](https://peps.python.org/pep-0749/)
