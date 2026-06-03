---
id: django-json-field
title: Use Built-in JSONField Instead of contrib.postgres
category: django
layer: 2
tags:
  - django
  - jsonfield
  - models
  - database
aliases:
  - postgres-jsonfield
  - contrib-jsonfield
python: ">=3.9"
frequency: high
detect-patterns:
  - "from django\.contrib\.postgres\.fields import.*JSONField"
---

# Use Built-in JSONField

Use `django.db.models.JSONField` instead of `django.contrib.postgres.fields.JSONField`. The built-in version works with all database backends.

## BAD

```python
from django.contrib.postgres.fields import JSONField
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=200)
    metadata = JSONField(default=dict)
```

## GOOD

```python
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=200)
    metadata = models.JSONField(default=dict)
```

## Why

- `contrib.postgres.JSONField` only works with PostgreSQL
- `models.JSONField` works with SQLite (JSON1 extension; built-in since 3.38), PostgreSQL, MariaDB (10.2.7+), and MySQL (5.7.8+)
- The postgres version was deprecated in Django 3.1 and removed in Django 4.0
- mpg pre-generation guidance ensures the cross-database version is used from the start

## Version Notes

- `models.JSONField` available since Django 3.1 (2020-08)
- `contrib.postgres.JSONField` removed in Django 4.0

## References

- [Django JSONField](https://docs.djangoproject.com/en/5.2/ref/models/fields/#jsonfield)
- [Django 3.1 Release Notes](https://docs.djangoproject.com/en/5.2/releases/3.1/#jsonfield-for-all-supported-database-backends)
