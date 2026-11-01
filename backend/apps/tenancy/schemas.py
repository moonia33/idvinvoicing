from datetime import date

from ninja import Schema

from apps.tenancy.models import SellerProfile


class LoginIn(Schema):
    username: str
    password: str


class TenantOut(Schema):
    id: int
    name: str
    role: str


class MeOut(Schema):
    id: int
    username: str
    email: str
    tenants: list[TenantOut]
    current_tenant_id: int | None


class TenantIn(Schema):
    name: str


class TenantSwitchIn(Schema):
    tenant_id: int


class ProfileIn(Schema):
    seller_name: str
    activity_code: str = ""
    personal_code: str = ""
    vat_code: str = ""
    address: str = ""
    bank_name: str = ""
    iban: str = ""
    email: str = ""
    phone: str = ""
    invoice_series: str = "SF"
    accounting_basis: SellerProfile.AccountingBasis = SellerProfile.AccountingBasis.CASH
    deductions_method: SellerProfile.DeductionsMethod = SellerProfile.DeductionsMethod.PCT30
    insured_elsewhere: bool = False
    pension_accrual: bool = False
    vsd_holiday: bool = False
    sodra_exempt: bool = False
    activity_start: date | None = None


class ProfileOut(ProfileIn):
    logo: str = ""
