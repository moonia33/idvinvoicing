from django.db import models


class DocumentSequence(models.Model):
    """Nuosekli dokumentų numeracija per tenant + rūšis + serija + metai."""

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="document_sequences"
    )
    kind = models.CharField(max_length=30)
    series = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "kind", "series", "year"], name="unique_document_sequence"
            )
        ]

    def __str__(self):
        return f"{self.kind}/{self.series}/{self.year}: {self.last_number}"
