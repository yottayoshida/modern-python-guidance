---
id: match-case-patterns
title: Use Structural Pattern Matching
category: data-structures
layer: 1
tags:
  - match
  - pattern-matching
  - control-flow
aliases:
  - match case
  - switch case
  - pattern matching
python: ">=3.10"
frequency: medium
pep: 634
---

# Use Structural Pattern Matching

Since Python 3.10, use `match`/`case` for complex conditional logic involving structure, type, and value checks.

## BAD

```python
def handle_command(command):
    if isinstance(command, dict):
        if "action" in command and command["action"] == "move":
            x = command.get("x", 0)
            y = command.get("y", 0)
            return move(x, y)
        elif "action" in command and command["action"] == "resize":
            return resize(command.get("width"), command.get("height"))
    elif isinstance(command, list) and len(command) == 2:
        return move(*command)
    raise ValueError(f"Unknown command: {command}")
```

## GOOD

```python
def handle_command(command):
    match command:
        case {"action": "move", "x": x, "y": y}:
            return move(x, y)
        case {"action": "resize", "width": w, "height": h}:
            return resize(w, h)
        case [x, y]:
            return move(x, y)
        case _:
            raise ValueError(f"Unknown command: {command}")
```

## Why

- Destructures and binds in one step
- Handles dicts, sequences, classes, and literals uniformly
- Guard clauses with `case ... if condition:`
- `_` wildcard is explicit "match anything"
- More readable than nested `if/isinstance/in` chains

## Version Notes

- 3.10+: `match`/`case` statements
- Not a switch statement — it's structural pattern matching with binding

## References

- [PEP 634 — Structural Pattern Matching: Specification](https://peps.python.org/pep-0634/)
- [PEP 636 — Structural Pattern Matching: Tutorial](https://peps.python.org/pep-0636/)
