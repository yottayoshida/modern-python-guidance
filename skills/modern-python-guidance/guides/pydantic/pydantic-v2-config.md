---
id: pydantic-v2-config
title: Use model_config Instead of class Config
category: pydantic
layer: 2
tags:
  - pydantic
  - config
  - migration
aliases:
  - class Config
  - model_config
  - ConfigDict
python: ">=3.9"
frequency: high
detect-patterns:
  - "class Config:"
---

# Use model_config Instead of class Config

Pydantic V2 replaces the inner `class Config` with a module-level `model_config` dict.

## BAD

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

    class Config:
        str_strip_whitespace = True
        from_attributes = True
        json_schema_extra = {"examples": [{"name": "Alice"}]}
```

## GOOD

```python
from pydantic import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        from_attributes=True,
        json_schema_extra={"examples": [{"name": "Alice"}]},
    )

    name: str
    email: str
```

## Why

- `class Config` is deprecated in Pydantic V2 (removed in V3)
- `ConfigDict` is typed — IDE autocompletion and type checking work
- Some V1 config keys were renamed (`orm_mode` → `from_attributes`, `allow_population_by_field_name` → `populate_by_name`)
- `model_config` is a class variable, not a nested class — simpler inheritance

## Migration Quick Reference

| V1 (class Config) | V2 (ConfigDict) |
|----|-----|
| `orm_mode = True` | `from_attributes=True` |
| `allow_population_by_field_name = True` | `populate_by_name=True` |
| `anystr_strip_whitespace = True` | `str_strip_whitespace=True` |
| `validate_assignment = True` | `validate_assignment=True` |
| `use_enum_values = True` | `use_enum_values=True` |

## References

- [Pydantic V2 Configuration](https://docs.pydantic.dev/latest/concepts/config/)
- [Pydantic V2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
