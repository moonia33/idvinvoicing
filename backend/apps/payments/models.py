from decimal import Decimal

from django.db import models

from apps.tenancy.models import Tenant

ZERO = Decimal("0.00")


class MoneyTransfer(models.Model):
    """Pinigų judėjimas (banko operacija, grynieji). Dokumentus dengia per
    `Payment` (sąskaitos) ir `PurchasePayment` (pirkimai) – sudengimus."""

    class Direction(models.TextChoices):
        IN = "in", "Gauta"
        OUT = "out", "Sumokėta"

    class Method(models.TextChoices):
        BANK = "bank", "Banko pavedimas"
        CASH = "cash", "Grynieji"
        CARD = "card", "Banko kortele"
        OTHER = "other", "Kita"

    class Currency(models.TextChoices):
        EUR = "EUR", "EUR"
        PLN = "PLN", "PLN"

    class Source(models.TextChoices):
        MANUAL = "manual", "Rankinis"
        IMPORT = "import", "Banko išrašas"

    class Status(models.TextChoices):
        UNALLOCATED = "unallocated", "Nesudengta"
        PARTIAL = "partial", "Dalinai sudengta"
        ALLOCATED = "allocated", "Sudengta"
        IGNORED = "ignored", "Neapskaitoma"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="transfers")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EUR)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    counterparty = models.ForeignKey(
        "invoicing.Counterparty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers",
    )
    counterparty_name = models.CharField("Kontragentas (iš banko)", max_length=200, blank=True)
    counterparty_iban = models.CharField("Kontragento IBAN", max_length=34, blank=True)
    reference = models.CharField("Mokėjimo paskirtis", max_length=500, blank=True)
    note = models.CharField(max_length=200, blank=True)
    ignored = models.BooleanField("Neapskaitoma", default=False)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    account_iban = models.CharField("Sąskaita (išrašas)", max_length=34, blank=True)
    external_id = models.CharField("Banko operacijos ID", max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "account_iban", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_transfer_external_id",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="transfer_amount_gt_0"),
        ]

    def __str__(self):
        return f"{self.get_direction_display()} {self.amount} {self.currency} {self.date}"

    def allocation_amount(self, alloc) -> Decimal:
        """Sudengimo suma mokėjimo valiuta."""
        if hasattr(alloc, "invoice_id"):
            return alloc.amount
        if alloc.purchase.currency == self.currency:
            return alloc.amount_original
        return alloc.amount_eur

    @property
    def allocated_total(self) -> Decimal:
        total = sum((a.amount for a in self.invoice_allocations.all()), ZERO)
        total += sum((self.allocation_amount(a) for a in self.purchase_allocations.all()), ZERO)
        return total

    @property
    def unallocated(self) -> Decimal:
        return self.amount - self.allocated_total

    @property
    def status(self) -> str:
        if self.ignored:
            return self.Status.IGNORED
        allocated = self.allocated_total
        if allocated <= 0:
            return self.Status.UNALLOCATED
        if allocated < self.amount:
            return self.Status.PARTIAL
        return self.Status.ALLOCATED
