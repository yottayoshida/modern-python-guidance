---
id: fastapi-annotated-depends
title: Use Annotated for Dependency Injection
category: fastapi
layer: 2
tags:
  - fastapi
  - dependency-injection
  - annotated
aliases:
  - Depends
  - Annotated
  - dependency injection
python: ">=3.9"
frequency: high
---

# Use Annotated for Dependency Injection

Since FastAPI 0.95.0, use `Annotated[T, Depends(...)]` instead of bare `Depends()` as default values.

## BAD

```python
from fastapi import Depends, FastAPI

app = FastAPI()

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
async def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

## GOOD

```python
from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

DbDep = Annotated[Session, Depends(get_db)]

@app.get("/users")
async def list_users(db: DbDep):
    return db.query(User).all()
```

## Why

- `Annotated` keeps the type and the dependency together — reusable as a type alias
- Default values with `Depends()` don't work well with non-FastAPI callers (e.g., tests)
- `Annotated` is the standard Python way to attach metadata to types (PEP 593)
- Multiple dependencies can be composed into a single type alias

## Version Notes

- `Annotated` available from `typing` since 3.9
- FastAPI `Annotated` support since 0.95.0 (2023-04)
- Also works for `Query`, `Path`, `Body`, `Header`, `Cookie`, `Form`, `File`

## References

- [FastAPI Dependencies with Annotated](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [PEP 593 — Flexible function and variable annotations](https://peps.python.org/pep-0593/)
