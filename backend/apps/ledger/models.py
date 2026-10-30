from decimal import Decimal

from django.db import models

from apps.tenancy.models import Tenant


class Category(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Pajamos"
        EXPENSE = "expense", "Išlaidos"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="categories")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=100)
    is_deductible = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "name"], name="unique_category_name")
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"


class LedgerEntry(models.Model):
    """Žurnalo įrašas: išlaida arba ne sąskaitinė pajama.

    Pirkimai gali būti PLN – konversija rankinė per `exchange_rate`,
    `amount_eur` suskaičiuojamas automatiškai.
    """

    class Kind(models.TextChoices):
        INCOME = "income", "Pajamos"
        EXPENSE = "expense", "Išlaidos"

    class Currency(models.TextChoices):
        EUR = "EUR", "EUR"
        PLN = "PLN", "PLN"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ledger_entries")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="entries"
    )
    document_date = models.DateField("Dokumento data")
    paid_date = models.DateField("Apmokėjimo data")
    counterparty = models.CharField("Tiekėjas / mokėtojas", max_length=200, blank=True)
    description = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EUR)
    amount_original = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("1"))
    amount_eur = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    class TaxKind(models.TextChoices):
        NONE = "", "—"
        GPM = "gpm", "GPM"
        VSD = "vsd", "VSD"
        PSD = "psd", "PSD"

    deductible = models.BooleanField("Leidžiami atskaitymai", default=True)
    tax_kind = models.CharField(
        "Mokesčio rūšis",
        max_length=4,
        choices=TaxKind.choices,
        default=TaxKind.NONE,
        blank=True,
    )
    tax_year = models.PositiveIntegerField("Už kuriuos metus mokestis", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-document_date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount_eur} EUR ({self.document_date})"

    def save(self, *args, **kwargs):
        self.amount_eur = (self.amount_original * self.exchange_rate).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
