from decimal import Decimal

from django.db import models

from apps.tenancy.models import Tenant


class Counterparty(models.Model):
    """Bendra kontaktų lentelė: klientai (pardavimai) ir tiekėjai (pirkimai)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="counterparties")
    name = models.CharField(max_length=200)
    code = models.CharField("Įmonės / asmens kodas", max_length=50, blank=True)
    vat_code = models.CharField("PVM kodas", max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    is_client = models.BooleanField("Klientas", default=True)
    is_supplier = models.BooleanField("Tiekėjas", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Service(models.Model):
    """Prekės/paslaugos katalogo įrašas – eilučių pildymas sąskaitose ir pirkimuose."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="services")
    category = models.ForeignKey(
        "ledger.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services",
    )
    code = models.CharField("Prekės/paslaugos kodas", max_length=50, blank=True)
    name = models.CharField(max_length=200)
    unit = models.CharField("Vienetas", max_length=20, default="vnt.")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_sale = models.BooleanField("Pardavimams", default=True)
    is_purchase = models.BooleanField("Pirkimams", default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code + ' ' if self.code else ''}{self.name}"


class InvoiceSeries(models.Model):
    """Sąskaitų serijos per veiklą: viena numatytoji + papildomos.

    Papildoma serija (pvz. „SFK") leidžia teisėtai išrašyti sąskaitą
    atgaline data – kiekviena serija turi atskirą numeracijos seką.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="invoice_series_set"
    )
    code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_invoice_series_code"
            )
        ]

    def __str__(self):
        return self.code


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Juodraštis"
        ISSUED = "issued", "Išrašyta"
        PARTIALLY_PAID = "partially_paid", "Daliniai apmokėta"
        PAID = "paid", "Apmokėta"
        CANCELLED = "cancelled", "Atšaukta"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoices")
    client = models.ForeignKey(
        Counterparty, on_delete=models.PROTECT, related_name="invoices"
    )
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
        CARD = "card", "Banko kortele"
        OTHER = "other", "Kita"

    class DocType(models.TextChoices):
        NONE = "", "Be dokumento"
        KPO = "kpo", "Kasos pajamų orderis (KPO)"
        PPK = "ppk", "Pinigų priėmimo kvitas (PPK)"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    doc_type = models.CharField(
        max_length=4, choices=DocType.choices, default=DocType.NONE, blank=True
    )
    doc_number = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_at", "id"]

    def __str__(self):
        return f"{self.amount} {self.invoice_id}"


class RecurringTemplate(models.Model):
    """Periodinių sąskaitų šablonas – qcluster generuoja pagal next_run_date."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Kas mėnesį"
        QUARTERLY = "quarterly", "Kas ketvirtį"
        YEARLY = "yearly", "Kas metus"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="recurring_templates")
    client = models.ForeignKey(
        Counterparty, on_delete=models.PROTECT, related_name="recurring_templates"
    )
    series = models.CharField(max_length=10, default="SF")
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    next_run_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    auto_send = models.BooleanField(default=False)
    email_to = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_run_date"]

    def __str__(self):
        return f"{self.client} – {self.get_frequency_display()}"


class RecurringLine(models.Model):
    template = models.ForeignKey(RecurringTemplate, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("1"))
    unit = models.CharField(max_length=20, default="vnt.")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))
