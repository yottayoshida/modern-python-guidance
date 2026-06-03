---
id: sqlalchemy-mapped-column
title: Use Mapped and mapped_column for Model Definitions
category: sqlalchemy
layer: 2
tags:
  - sqlalchemy
  - orm
  - mapped-column
  - declarative
aliases:
  - Column
  - declarative-base
python: ">=3.9"
frequency: high
detect-patterns:
  - "from sqlalchemy import .*\bColumn\b"
  - "declarative_base\("
---

# Use Mapped and mapped_column

Define ORM models with `Mapped[T]` type annotations and `mapped_column()` instead of bare `Column()`. Type information is inferred from the annotation.

## BAD

```python
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
```

## GOOD

```python
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
```

## Why

- `Mapped[str]` implies NOT NULL; `Mapped[str | None]` implies nullable -- nullability is declared by the type annotation
- Type checkers (mypy, pyright) understand column types without plugins
- `DeclarativeBase` class replaces the `declarative_base()` function
- No Ruff rules cover this pattern -- mpg ensures modern declarative style from the start

## Version Notes

- SQLAlchemy 2.0+ (released 2023-01)
- `declarative_base()` function still works but is considered legacy
- String length (`String(100)`) is still required for VARCHAR columns

## References

- [Declarative Tables with mapped_column()](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- [Mapped Column API](https://docs.sqlalchemy.org/en/20/orm/mapping_api.html#sqlalchemy.orm.mapped_column)
