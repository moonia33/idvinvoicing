from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.ledger.models import LedgerEntry
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
    paid: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")

    def __post_init__(self):
        self.base = _q(self.base)
        self.amount = _q(self.amount)
        self.paid = _q(self.paid)
        self.remaining = _q(self.remaining)


@dataclass
class MonthRow:
    month: int
    income: Decimal
    profit: Decimal
    vsd: Decimal
    psd: Decimal


@dataclass
class TaxBreakdown:
    year: int
    months: int
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
    paid_total: Decimal
    remaining_total: Decimal
    monthly: list[MonthRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def default_months(year: int, today: date | None = None) -> int:
    """Kiek metų mėnesių įtraukti: einamieji – iki einamojo mėn., kiti – 12."""
    today = today or date.today()
    if year < today.year:
        return 12
    if year > today.year:
        return 1
    return today.month


def annual_totals(tenant: Tenant, year: int, months: int = 12) -> tuple[Decimal, Decimal, Decimal]:
    """(pajamos, visos išlaidos, leidžiami atskaitymai) už months mėnesių."""
    income = expenses = deductible = Decimal("0")
    for month in range(1, months + 1):
        s = journal_summary(journal_rows(tenant, year, month))
        income += s["income_total"]
        expenses += s["expense_total"]
        deductible += s["deductible_total"]
    return _q(income), _q(expenses), _q(deductible)


def _tax_paid(tenant: Tenant, kind: str, year: int) -> Decimal:
    return _q(
        sum(
            LedgerEntry.objects.filter(tenant=tenant, tax_kind=kind, tax_year=year).values_list(
                "amount_eur", flat=True
            )
        )
        or Decimal("0")
    )


def _gpm(profit: Decimal, rule: TaxRule) -> TaxLine:
    if profit <= 0:
        return TaxLine(Decimal("0"), rule.gpm_rate, Decimal("0"))
    if profit <= rule.gpm_soft_cap:
        # Lengvatine formulė: P x (gpm_rate - coef x (1 - P/soft_cap))
        effective = rule.gpm_rate - rule.gpm_reduction_coef * (1 - profit / rule.gpm_soft_cap)
        return TaxLine(profit, effective, _q(profit * effective), "lengvatinė GPM formulė")
    return TaxLine(profit, rule.gpm_rate, _q(profit * rule.gpm_rate))


def _social(
    profit: Decimal,
    rate: Decimal,
    rule: TaxRule,
    months: int,
    exempt: bool,
    no_minimum: bool = False,
) -> TaxLine:
    if exempt or profit <= 0:
        return TaxLine(Decimal("0"), rate, Decimal("0"))
    base = profit * rule.social_base_share
    note = ""
    min_base = rule.mma_monthly * months
    if not no_minimum and base < min_base:
        base, note = min_base, f"taikyta minimali bazė ({months} x MMA)"
    if base > rule.annual_cap:
        base, note = rule.annual_cap, "taikyta maksimali metinė bazė (43 x VDU)"
    return TaxLine(_q(base), rate, _q(base * rate), note)


def compute_taxes(
    tenant: Tenant,
    year: int,
    months: int | None = None,
    psd_paid_elsewhere: bool = False,
) -> TaxBreakdown:
    rule = TaxRule.objects.filter(year__lte=year).order_by("-year").first()
    warnings: list[str] = []
    if rule is None:
        rule = TaxRule()
        warnings.append("Mokesčių taisyklės nerastos – naudojamos numatytosios.")
    elif rule.year != year:
        warnings.append(f"Naudojamos {rule.year} m. taisyklės {year} m. skaičiavimui.")

    months = max(1, min(12, months if months is not None else default_months(year)))
    income, expenses, deductible = annual_totals(tenant, year, months)

    profile = getattr(tenant, "profile", None)
    method = (
        profile.deductions_method if profile is not None else SellerProfile.DeductionsMethod.PCT30
    )
    insured = bool(getattr(profile, "insured_elsewhere", False))

    applied_pct30 = _q(income * rule.fixed_deduction_rate)
    applied = applied_pct30 if method == SellerProfile.DeductionsMethod.PCT30 else deductible
    recommended = (
        SellerProfile.DeductionsMethod.PCT30
        if applied_pct30 >= deductible
        else SellerProfile.DeductionsMethod.ACTUAL
    )

    profit = _q(max(income - applied, Decimal("0")))
    gpm = _gpm(profit, rule)
    vsd = _social(profit, rule.vsd_rate, rule, months, exempt=False, no_minimum=insured)
    psd = _social(profit, rule.psd_rate, rule, months, exempt=insured or psd_paid_elsewhere)

    for line, kind in ((gpm, "gpm"), (vsd, "vsd"), (psd, "psd")):
        line.paid = _tax_paid(tenant, kind, year)
        line.remaining = _q(max(line.amount - line.paid, Decimal("0")))

    # Mėnesių suvestinė: pajamos/pelnas per mėn. + mėnesinės VSD/PSD įmokos.
    monthly: list[MonthRow] = []
    for m in range(1, months + 1):
        s = journal_summary(journal_rows(tenant, year, m))
        m_income = s["income_total"]
        m_ded = (
            m_income * rule.fixed_deduction_rate
            if method == SellerProfile.DeductionsMethod.PCT30
            else s["deductible_total"]
        )
        m_profit = _q(max(m_income - m_ded, Decimal("0")))
        if insured:
            psd_m = Decimal("0")
            vsd_m = _q(m_profit * rule.social_base_share * rule.vsd_rate)
        else:
            psd_m = _q(rule.psd_rate * rule.mma_monthly)
            vsd_m = _q(
                max(
                    m_profit * rule.social_base_share * rule.vsd_rate,
                    rule.vsd_rate * rule.mma_monthly,
                )
            )
        monthly.append(MonthRow(m, _q(m_income), m_profit, _q(vsd_m), _q(psd_m)))

    paid_total = gpm.paid + vsd.paid + psd.paid
    remaining_total = gpm.remaining + vsd.remaining + psd.remaining

    return TaxBreakdown(
        year=year,
        months=months,
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
        paid_total=_q(paid_total),
        remaining_total=_q(remaining_total),
        monthly=monthly,
        warnings=warnings,
    )
