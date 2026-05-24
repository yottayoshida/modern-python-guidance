---
id: pydantic-v2-serialization
title: Use field_serializer for Custom Serialization
category: pydantic
layer: 2
tags:
  - pydantic
  - serialization
  - migration
aliases:
  - field_serializer
  - model_serializer
  - json_encoders
python: ">=3.9"
frequency: medium
---

# Use field_serializer for Custom Serialization

Pydantic V2 replaces `json_encoders` in Config with `@field_serializer` and `@model_serializer` decorators.

## BAD

```python
from datetime import datetime
from pydantic import BaseModel

class Event(BaseModel):
    name: str
    timestamp: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
```

## GOOD

```python
from datetime import datetime
from pydantic import BaseModel, field_serializer

class Event(BaseModel):
    name: str
    timestamp: datetime

    @field_serializer("timestamp")
    @classmethod
    def serialize_timestamp(cls, v: datetime) -> str:
        return v.isoformat()
```

## Why

- `json_encoders` is removed in Pydantic V2
- `@field_serializer` is explicit about which fields it handles
- Type-safe — serializer input/output types are checked
- `@model_serializer` replaces whole-model custom serialization
- `mode="plain"` or `mode="wrap"` controls whether the default serializer runs first

## Serializer Modes

| Mode | Behavior |
|------|---------|
| `mode="plain"` (default) | Replaces the default serializer entirely |
| `mode="wrap"` | Receives the default serializer as a callable, can modify its output |

## References

- [Pydantic V2 Serialization](https://docs.pydantic.dev/latest/concepts/serialization/)
