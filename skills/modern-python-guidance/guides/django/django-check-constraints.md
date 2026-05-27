---
id: django-check-constraints
title: Use condition Parameter in CheckConstraint
category: django
layer: 2
tags:
  - django
  - constraints
  - models
  - database
aliases:
  - check-constraint
python: ">=3.9"
frequency: low
---

# Use condition Instead of check in CheckConstraint

The `check` parameter of `CheckConstraint` was renamed to `condition` in Django 5.1 and removed in Django 6.0.

## BAD

```python
from django.db import models

class Order(models.Model):
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name="order_quantity_positive",
            ),
        ]
```

## GOOD

```python
from django.db import models

class Order(models.Model):
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="order_quantity_positive",
            ),
        ]
```

## Why

- `check=` was deprecated in Django 5.1 with `RemovedInDjango60Warning`
- `check=` was removed in Django 6.0 -- code using it will raise `TypeError`
- The rename aligns `CheckConstraint` with `UniqueConstraint(condition=)` for consistency
- mpg pre-generation guidance prevents deprecated parameter usage from the start

## Version Notes

- Django 5.1+: `condition` parameter added, `check` deprecated
- Django 6.0: `check` parameter removed
- For Django < 5.1, `check=` is the only option

## References

- [Django CheckConstraint](https://docs.djangoproject.com/en/6.0/ref/models/constraints/#django.db.models.CheckConstraint)
- [Django 5.1 Release Notes](https://docs.djangoproject.com/en/6.0/releases/5.1/#features-deprecated-in-5-1)
