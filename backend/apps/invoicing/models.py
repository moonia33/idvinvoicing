from decimal import Decimal

from django.db import models

from apps.tenancy.models import Tenant


class Client(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=200)
    code = models.CharField("Įmonės / asmens kodas", max_length=50, blank=True)
    vat_code = models.CharField("PVM kodas", max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Juodraštis"
        ISSUED = "issued", "Išrašyta"
        PARTIALLY_PAID = "partially_paid", "Daliniai apmokėta"
        PAID = "paid", "Apmokėta"
        CANCELLED = "cancelled", "Atšaukta"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoices")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="invoices")
    series = models.CharField(max_length=10, default="SF")
    year = models.PositiveIntegerField(null=True, blank=True)
    number = models.PositiveIntegerField(null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "series", "year", "number"], name="unique_invoice_number"
            )
        ]

    def __str__(self):
        return self.full_number or f"Juodraštis #{self.pk}"

    @property
    def full_number(self) -> str | None:
        if self.number is None or self.year is None:
            return None
        return f"{self.series}-{self.year}-{self.number:04d}"

    @property
    def paid_total(self) -> Decimal:
        return sum((p.amount for p in self.payments.all()), Decimal("0.00"))

    def recalc_total(self) -> None:
        self.total = sum((line.total for line in self.lines.all()), Decimal("0.00"))

    def recalc_status(self) -> None:
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return
        paid = self.paid_total
        if paid <= 0:
            self.status = self.Status.ISSUED
        elif paid < self.total:
            self.status = self.Status.PARTIALLY_PAID
        else:
            self.status = self.Status.PAID


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("1"))
    unit = models.CharField(max_length=20, default="vnt.")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class Payment(models.Model):
    class Method(models.TextChoices):
        BANK = "bank", "Banko pavedimas"
        CASH = "cash", "Grynieji"
        OTHER = "other", "Kita"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_at", "id"]

    def __str__(self):
        return f"{self.amount} {self.invoice_id}"
