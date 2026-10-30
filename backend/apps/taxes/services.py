from dataclasses import dataclass
from decimal import Decimal

from apps.ledger.services import journal_rows, journal_summary
from apps.taxes.models import TaxRule
from apps.tenancy.models import SellerProfile, Tenant

Q = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Q)


@dataclass
class TaxLine:
    base: Decimal
    rate: Decimal
    amount: Decimal
    note: str = ""

    def __post_init__(self):
        self.base = _q(self.base)
        self.amount = _q(self.amount)


@dataclass
class TaxBreakdown:
    year: int
    income_total: Decimal
    expenses_total: Decimal
    deductible_total: Decimal
    deductions_method: str
    deductions_applied: Decimal
    recommended_deductions_method: str
    profit: Decimal
    gpm: TaxLine
    vsd: TaxLine
    psd: TaxLine
    total: Decimal
    warnings: list[str]


def annual_totals(tenant: Tenant, year: int) -> tuple[Decimal, Decimal, Decimal]:
    """(pajamos, visos išlaidos, leidžiami atskaitymai) už metus pagal accounting_basis."""
    income = expenses = deductible = Decimal("0")
    for month in range(1, 13):
        s = journal_summary(journal_rows(tenant, year, month))
        income += s["income_total"]
        expenses += s["expense_total"]
        deductible += s["deductible_total"]
    return _q(income), _q(expenses), _q(deductible)


def _gpm(profit: Decimal, rule: TaxRule) -> TaxLine:
    if profit <= 0:
        return TaxLine(Decimal("0"), rule.gpm_rate, Decimal("0"))
    if profit <= rule.gpm_soft_cap:
        # Lengvatine formulė: P x (gpm_rate - coef x (1 - P/soft_cap))
        effective = rule.gpm_rate - rule.gpm_reduction_coef * (1 - profit / rule.gpm_soft_cap)
        return TaxLine(profit, effective, _q(profit * effective), "lengvatinė GPM formulė")
    return TaxLine(profit, rule.gpm_rate, _q(profit * rule.gpm_rate))


def _social(profit: Decimal, rate: Decimal, rule: TaxRule, exempt: bool) -> TaxLine:
    if exempt or profit <= 0:
        return TaxLine(Decimal("0"), rate, Decimal("0"))
    base = profit * rule.social_base_share
    min_base = rule.mma_monthly * 12
    note = ""
    if base < min_base:
        base, note = min_base, "taikyta minimali metinė bazė (12 x MMA)"
    if base > rule.annual_cap:
        base, note = rule.annual_cap, "taikyta maksimali metinė bazė (43 x VDU)"
    return TaxLine(_q(base), rate, _q(base * rate), note)


def compute_taxes(tenant: Tenant, year: int, psd_paid_elsewhere: bool = False) -> TaxBreakdown:
    rule = TaxRule.objects.filter(year__lte=year).order_by("-year").first()
    warnings: list[str] = []
    if rule is None:
        rule = TaxRule()
        warnings.append("Mokesčių taisyklės nerastos – naudojamos numatytosios.")
    elif rule.year != year:
        warnings.append(f"Naudojamos {rule.year} m. taisyklės {year} m. skaičiavimui.")

    income, expenses, deductible = annual_totals(tenant, year)

    profile = getattr(tenant, "profile", None)
    method = (
        profile.deductions_method if profile is not None else SellerProfile.DeductionsMethod.PCT30
    )
    applied_pct30 = _q(income * rule.fixed_deduction_rate)
    applied = applied_pct30 if method == SellerProfile.DeductionsMethod.PCT30 else deductible
    recommended = (
        SellerProfile.DeductionsMethod.PCT30
        if applied_pct30 >= deductible
        else SellerProfile.DeductionsMethod.ACTUAL
    )

    profit = _q(max(income - applied, Decimal("0")))
    gpm = _gpm(profit, rule)
    vsd = _social(profit, rule.vsd_rate, rule, exempt=False)
    psd = _social(profit, rule.psd_rate, rule, exempt=psd_paid_elsewhere)

    return TaxBreakdown(
        year=year,
        income_total=income,
        expenses_total=expenses,
        deductible_total=deductible,
        deductions_method=method,
        deductions_applied=applied,
        recommended_deductions_method=recommended,
        profit=profit,
        gpm=gpm,
        vsd=vsd,
        psd=psd,
        total=_q(gpm.amount + vsd.amount + psd.amount),
        warnings=warnings,
    )
