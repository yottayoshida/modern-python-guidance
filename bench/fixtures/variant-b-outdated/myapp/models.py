from django.db import models
from django.contrib.postgres.fields import JSONField


class Product(models.Model):
    name = models.CharField(max_length=200)
    metadata = JSONField(default=dict)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name="price_non_negative",
            ),
        ]
