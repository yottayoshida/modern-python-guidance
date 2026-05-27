from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=200)
    metadata = models.JSONField(default=dict)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="price_non_negative",
            ),
        ]
