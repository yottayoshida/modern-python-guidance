---
id: template-strings
title: Use Template Strings (t-strings) for Structured String Processing
category: stdlib
layer: 1
tags:
  - strings
  - templates
  - security
  - sql
aliases:
  - t-string
  - 't"'
  - Template
  - string.templatelib
python: ">=3.14"
frequency: medium
pep: 750
---

# Use Template Strings for Structured String Processing

Python 3.14 introduces t-strings (PEP 750): a `t"..."` prefix that produces a `Template` object instead of a `str`. Pass the `Template` to a processing function that separates literal text from interpolated values, enabling safe parameterization for SQL, HTML, shell commands, and other injection-sensitive contexts.

## BAD

```python
def query_user(db, user_id: str) -> dict:
    sql = f"SELECT * FROM users WHERE id = '{user_id}'"
    return db.execute(sql).fetchone()
```

## GOOD

```python
from string.templatelib import Interpolation

def sql(template) -> tuple[str, list]:
    parts, params = [], []
    for item in template:
        if isinstance(item, Interpolation):
            parts.append("?")
            params.append(item.value)
        else:
            parts.append(item)
    return "".join(parts), params

def query_user(db, user_id: str) -> dict:
    query, params = sql(t"SELECT * FROM users WHERE id = {user_id}")
    return db.execute(query, params).fetchone()
```

## Why

- f-strings produce a final `str` with interpolated values already baked in, making it impossible to distinguish user input from literal SQL after the fact
- t-strings produce a `Template` that preserves the structure: literal segments as strings, interpolated values as `Interpolation` objects with `value`, `expression`, `conversion`, and `format_spec` attributes
- A processing function can then route each interpolated value through proper escaping or parameterization, preventing injection by construction
- t-strings do NOT make strings safe by themselves -- safety comes entirely from the processing function that receives the `Template`

## Version Notes

- 3.14+: `t"..."` syntax and `string.templatelib` module (`Template`, `Interpolation`)
- Pre-3.14: Use parameterized queries directly (`db.execute("SELECT ... WHERE id = ?", [user_id])`) or template engines with auto-escaping
- For simple string formatting where injection is not a concern, f-strings remain the appropriate choice
- `Template` objects do not render to `str` automatically -- a processing function is always required

## References

- [PEP 750 -- Template Strings](https://peps.python.org/pep-0750/)
- [string.templatelib documentation](https://docs.python.org/3/library/string.templatelib.html)
