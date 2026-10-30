from decimal import Decimal

from ninja import Schema


class TaxRuleOut(Schema):
    year: int
    gpm_rate: Decimal
    gpm_flat_cap: Decimal
    gpm_progressive_cap: Decimal
    gpm_top_rate: Decimal
    fixed_deduction_rate: Decimal
    social_base_share: Decimal
    vsd_rate: Decimal
    vsd_rate_pension: Decimal
    psd_rate: Decimal
    mma_monthly: Decimal
    annual_cap: Decimal


class TaxLineOut(Schema):
    base: Decimal
    rate: Decimal
    amount: Decimal
    note: str
    paid: Decimal
    remaining: Decimal


class MonthRowOut(Schema):
    month: int
    income: Decimal
    profit: Decimal
    vsd: Decimal
    psd: Decimal


class TaxBreakdownOut(Schema):
    year: int
    months: int
    active_months: int
    income_total: Decimal
    expenses_total: Decimal
    deductible_total: Decimal
    deductions_method: str
    deductions_applied: Decimal
    recommended_deductions_method: str
    profit: Decimal
    gpm: TaxLineOut
    vsd: TaxLineOut
    psd: TaxLineOut
    total: Decimal
    paid_total: Decimal
    remaining_total: Decimal
    monthly: list[MonthRowOut]
    warnings: list[str]
