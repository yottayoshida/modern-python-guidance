---
id: sqlalchemy-2-style
title: Use SQLAlchemy 2.0 Query Style
category: sqlalchemy
layer: 2
tags:
  - sqlalchemy
  - query
  - select
  - orm
aliases:
  - session.query
  - legacy-query
python: ">=3.9"
frequency: high
detect-patterns:
  - "\.query\([A-Z]"
---

# Use SQLAlchemy 2.0 Query Style

Use `select()` with `session.execute()` instead of the legacy `session.query()` API. The 2.0 style unifies Core and ORM query construction.

## BAD

```python
from sqlalchemy.orm import Session

def get_active_users(session: Session):
    users = session.query(User).filter(
        User.is_active == True
    ).order_by(User.name).all()
    return users

def get_user_by_id(session: Session, user_id: int):
    return session.query(User).get(user_id)

def count_users(session: Session):
    return session.query(User).count()
```

## GOOD

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

def get_active_users(session: Session):
    stmt = select(User).where(
        User.is_active == True
    ).order_by(User.name)
    return list(session.scalars(stmt))

def get_user_by_id(session: Session, user_id: int):
    return session.get(User, user_id)

def count_users(session: Session):
    from sqlalchemy import func
    stmt = select(func.count()).select_from(User)
    return session.scalar(stmt)
```

## Why

- `select()` unifies Core and ORM into one query API
- Explicit `execute()` / `scalars()` makes the execution point clear
- `session.get()` replaces `query().get()` with identity-map lookup
- Type checkers can infer result types from `select(User)`
- No Ruff rules cover this pattern -- mpg pre-generation guidance prevents legacy query style from being generated in the first place

## Version Notes

- SQLAlchemy 2.0+ (released 2023-01). Available in 1.4 with `future=True`
- `session.query()` is not removed and has no removal timeline. This is a modern style recommendation, not a required migration

## References

- [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [Using SELECT Statements](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html)
