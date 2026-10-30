from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Vienas vartotojas gali priklausyti keliems tenant'ams (veikloms)."""

    pass


class Tenant(models.Model):
    """Veikla – atskira apskaitos erdvė (vienas asmuo gali turėti kelias)."""

    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Savininkas"
        MEMBER = "member", "Narys"
        ACCOUNTANT = "accountant", "Buhalteris"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OWNER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="unique_user_tenant")
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"


class SellerProfile(models.Model):
    """Pardavėjo (IV vykdytojo) rekvizitai ir nustatymai – DB, ne env."""

    class AccountingBasis(models.TextChoices):
        CASH = "cash", "Pinigų principas"
        ACCRUAL = "accrual", "Kaupimo principas"

    class DeductionsMethod(models.TextChoices):
        PCT30 = "pct30", "30% leidžiami atskaitymai"
        ACTUAL = "actual", "Faktinės išlaidos"

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="profile")
    seller_name = models.CharField(max_length=200)
    activity_code = models.CharField("Veiklos kodas / IV nr.", max_length=50, blank=True)
    personal_code = models.CharField("Asmens kodas", max_length=20, blank=True)
    vat_code = models.CharField("PVM kodas", max_length=20, blank=True)
    address = models.CharField(max_length=300, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    invoice_series = models.CharField(max_length=10, default="SF")
    accounting_basis = models.CharField(
        max_length=10, choices=AccountingBasis.choices, default=AccountingBasis.CASH
    )
    deductions_method = models.CharField(
        max_length=10, choices=DeductionsMethod.choices, default=DeductionsMethod.PCT30
    )
    insured_elsewhere = models.BooleanField(
        "Draustas kitur (dirba pagal darbo sutartį)", default=False
    )
    pension_accrual = models.BooleanField(
        "Papildomas pensijos kaupimas (VSD 15,52%)", default=False
    )
    vsd_holiday = models.BooleanField("Pirmoji veikla – VSD atostogos (iki 12 mėn.)", default=False)

    def __str__(self):
        return f"{self.seller_name} ({self.tenant})"
