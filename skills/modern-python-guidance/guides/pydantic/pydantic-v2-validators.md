---
id: pydantic-v2-validators
title: Use Pydantic V2 field_validator Instead of validator
category: pydantic
layer: 2
tags:
  - pydantic
  - validation
  - migration
aliases:
  - validator
  - field_validator
  - model_validator
python: ">=3.9"
frequency: high
---

# Use Pydantic V2 Validators

Pydantic V2 replaced `@validator` and `@root_validator` with `@field_validator` and `@model_validator`.

## BAD

```python
from pydantic import BaseModel, validator, root_validator

class User(BaseModel):
    name: str
    email: str

    @validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()

    @root_validator
    @classmethod
    def check_consistency(cls, values):
        return values
```

## GOOD

```python
from pydantic import BaseModel, field_validator, model_validator

class User(BaseModel):
    name: str
    email: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def check_consistency(self) -> "User":
        return self
```

## Why

- `@validator` and `@root_validator` are deprecated in Pydantic V2 (removed in V3)
- `@field_validator` is explicit about which fields it validates
- `@model_validator(mode="before"|"after")` replaces `@root_validator(pre=True|False)`
- `mode="after"` receives the model instance, not a raw dict

## Migration Quick Reference

| V1 | V2 |
|----|-----|
| `@validator("field")` | `@field_validator("field")` |
| `@validator("field", pre=True)` | `@field_validator("field", mode="before")` |
| `@root_validator` | `@model_validator(mode="after")` |
| `@root_validator(pre=True)` | `@model_validator(mode="before")` |

## References

- [Pydantic V2 Validators](https://docs.pydantic.dev/latest/concepts/validators/)
