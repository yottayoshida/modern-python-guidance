---
id: dict-merge-operator
title: Use | Operator for Dict Merging
category: data-structures
layer: 1
tags:
  - dict
  - merge
  - operator
aliases:
  - dict merge
  - dict update
  - "**kwargs"
python: ">=3.9"
frequency: medium
pep: 584
detect-patterns:
---

# Use | Operator for Dict Merging

Since Python 3.9, use the `|` operator to merge dictionaries instead of `{**d1, **d2}` or `dict.update()`.

## BAD

```python
defaults = {"timeout": 30, "retries": 3}
overrides = {"timeout": 60, "verbose": True}

# Unpacking merge — unclear precedence
config = {**defaults, **overrides}

# Mutates defaults
defaults.update(overrides)
```

## GOOD

```python
defaults = {"timeout": 30, "retries": 3}
overrides = {"timeout": 60, "verbose": True}

# Merge (right side wins on conflicts)
config = defaults | overrides

# In-place merge
defaults |= overrides
```

## Why

- Cleaner syntax: `d1 | d2` is immediately obvious
- Non-mutating by default (like set `|`)
- `|=` for in-place update (like `+=`)
- Works with dict subclasses (unlike `{**d1, **d2}`)

## Version Notes

- 3.9+: `dict.__or__` and `dict.__ior__`
- Pre-3.9: `{**d1, **d2}` or `d1.update(d2)` (mutating)

## References

- [PEP 584 — Add Union Operators To dict](https://peps.python.org/pep-0584/)
