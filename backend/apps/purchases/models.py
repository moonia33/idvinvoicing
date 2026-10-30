from decimal import Decimal

from django.db import models

from apps.tenancy.models import Tenant


class Supplier(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="suppliers")
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


class Purchase(models.Model):
    """Gautas išlaidų dokumentas (sąskaita/kvitas) su mokėjimais.

    Sudengimas pagal mokėjimus: statusas perskaičiuojamas pagal
    sumokėtą sumą originalo valiuta (`paid_total` vs `total`).
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Gauta"
        PARTIALLY_PAID = "partially_paid", "Dalinai apmokėta"
        PAID = "paid", "Apmokėta"
        CANCELLED = "cancelled", "Anuliuota"

    class Currency(models.TextChoices):
        EUR = "EUR", "EUR"
        PLN = "PLN", "PLN"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    doc_number = models.CharField("Tiekėjo dokumento nr.", max_length=60, blank=True)
    document_date = models.DateField("Dokumento data")
    due_date = models.DateField("Apmokėti iki", null=True, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EUR)
    exchange_rate = models.DecimalField(
        "Kursas -> EUR", max_digits=12, decimal_places=6, default=Decimal("1")
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    category = models.ForeignKey(
        "ledger.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchases",
        limit_choices_to={"kind": "expense"},
    )
    deductible = models.BooleanField("Leidžiami atskaitymai", default=True)
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-document_date", "-id"]

    def __str__(self):
        return f"{self.supplier} {self.doc_number or self.pk}"

    @property
    def paid_total(self) -> Decimal:
        return sum((p.amount_original for p in self.payments.all()), Decimal("0.00"))

    @property
    def total_eur(self) -> Decimal:
        return (self.total * self.exchange_rate).quantize(Decimal("0.01"))

    def recalc_total(self) -> None:
        self.total = sum((line.total for line in self.lines.all()), Decimal("0.00"))

    def recalc_status(self) -> None:
        if self.status == self.Status.CANCELLED:
            return
        paid = self.paid_total
        if paid <= 0:
            self.status = self.Status.RECEIVED
        elif paid < self.total:
            self.status = self.Status.PARTIALLY_PAID
        else:
            self.status = self.Status.PAID


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
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


class PurchasePayment(models.Model):
    """Mokėjimas už pirkinį: data, būdas, dokumento nr. (KIO auto / PPK / banko op.)."""

    class Method(models.TextChoices):
        BANK = "bank", "Banko pavedimas"
        CASH = "cash", "Grynieji"
        CARD = "card", "Banko kortele"
        OTHER = "other", "Kita"

    class DocType(models.TextChoices):
        NONE = "", "Be dokumento"
        KIO = "kio", "Kasos išlaidų orderis (KIO)"
        PPK = "ppk", "Pinigų priėmimo kvitas (PPK)"

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="payments")
    amount_original = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(
        "Kursas -> EUR", max_digits=12, decimal_places=6, default=Decimal("1")
    )
    amount_eur = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
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
        return f"{self.amount_original} {self.purchase_id}"

    def save(self, *args, **kwargs):
        self.amount_eur = (self.amount_original * self.exchange_rate).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
