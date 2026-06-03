---
id: pydantic-v2-model-api
title: Use Pydantic V2 model_validate Instead of parse_obj
category: pydantic
layer: 2
tags:
  - pydantic
  - validation
  - migration
aliases:
  - parse_obj
  - parse_raw
  - from_orm
  - model_validate
python: ">=3.9"
frequency: high
detect-patterns:
  - "\.parse_obj\("
  - "\.parse_raw\("
  - "\.from_orm\("
---

# Use Pydantic V2 Model API

Pydantic V2 renamed core model methods. The V1 names are removed.

## BAD

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int

# V1 API (removed in V2)
user = User.parse_obj({"name": "Alice", "age": 30})
user = User.parse_raw('{"name": "Alice", "age": 30}')
user = User.from_orm(db_user)
data = user.dict()
json_str = user.json()
schema = User.schema()
```

## GOOD

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int

# V2 API
user = User.model_validate({"name": "Alice", "age": 30})
user = User.model_validate_json('{"name": "Alice", "age": 30}')
data = user.model_dump()
json_str = user.model_dump_json()
json_schema = User.model_json_schema()
```

## Why

- V1 method names are removed in Pydantic V2
- `model_validate` is ~5-50x faster than V1's `parse_obj` (Rust core)
- `model_validate_json` parses JSON without intermediate dict
- Consistent `model_` prefix makes API discoverable

## Migration Quick Reference

| V1 | V2 |
|----|-----|
| `parse_obj(data)` | `model_validate(data)` |
| `parse_raw(json)` | `model_validate_json(json)` |
| `from_orm(obj)` | `model_validate(obj)` with `from_attributes=True` |
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `.schema()` | `.model_json_schema()` |
| `.copy()` | `.model_copy()` |

## References

- [Pydantic V2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
