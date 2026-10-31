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
    taxable_income: Decimal
    vsd: Decimal
    psd: Decimal


@dataclass
class TaxBreakdown:
    year: int
    months: int
    active_months: int
    income_total: Decimal
    expenses_total: Decimal
    deductible_total: Decimal
    deductions_method: str
    deductions_applied: Decimal
    recommended_deductions_method: str
    taxable_income: Decimal
    net_earning: Decimal
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


def _gpm(ap: Decimal, rule: TaxRule) -> TaxLine:
    """GPM 2025+: 5% iki flat_cap, linijinis 5->20% iki progressive_cap, 20% virš."""
    if ap <= 0:
        return TaxLine(Decimal("0"), rule.gpm_rate, Decimal("0"))
    if ap <= rule.gpm_flat_cap:
        return TaxLine(ap, rule.gpm_rate, _q(ap * rule.gpm_rate))
    if ap <= rule.gpm_progressive_cap:
        share = (ap - rule.gpm_flat_cap) / (rule.gpm_progressive_cap - rule.gpm_flat_cap)
        effective = rule.gpm_rate + (rule.gpm_top_rate - rule.gpm_rate) * share
        return TaxLine(ap, effective, _q(ap * effective), "progresinis GPM tarifas")
    return TaxLine(ap, rule.gpm_top_rate, _q(ap * rule.gpm_top_rate))


def _social(
    ap: Decimal,
    rate: Decimal,
    rule: TaxRule,
    months: int,
    exempt: bool = False,
    no_minimum: bool = False,
) -> TaxLine:
    if exempt or ap <= 0:
        return TaxLine(Decimal("0"), rate, Decimal("0"))
    base = ap * rule.social_base_share
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
    pension = bool(getattr(profile, "pension_accrual", False))
    vsd_relief = bool(getattr(profile, "vsd_holiday", False))
    if insured:
        warnings.append(
            "Draustas kitur: VSD/PSD be MMA minimumo, bet metų gale nuo 90 % AP vis tiek mokami."
        )
    if vsd_relief:
        warnings.append("Pirmoji veikla: VSD atostogos – įmokos nemokamos iki 12 mėn.")

    # Kiek langinio lango mėnesių veikla realiai vyko (minimumas – tik už juos)
    start = getattr(profile, "activity_start", None)
    if start is None or start.year < year:
        active_months = months
    elif start.year == year:
        active_months = max(0, months - start.month + 1)
    else:
        active_months = 0
    if start is not None and active_months < months:
        warnings.append(
            f"Minimali bazė proporcinga veiklos laikui: {active_months} mėn. "
            f"(veikla nuo {start:%Y-%m-%d})."
        )

    applied_pct30 = _q(income * rule.fixed_deduction_rate)
    applied = applied_pct30 if method == SellerProfile.DeductionsMethod.PCT30 else deductible
    recommended = (
        SellerProfile.DeductionsMethod.PCT30
        if applied_pct30 >= deductible
        else SellerProfile.DeductionsMethod.ACTUAL
    )

    taxable_income = _q(max(income - applied, Decimal("0")))
    if income > Decimal("45000"):
        warnings.append(
            "Pajamos viršijo 45 000 EUR – gali tekti registruotis PVM mokėtoju "
            "(nuo sandorio, kuriuo riba viršyta)."
        )
    gpm = _gpm(taxable_income, rule)
    vsd_rate = rule.vsd_rate_pension if pension else rule.vsd_rate
    # VSD individualiai veiklai – be MMA minimumo (tik metinė luba 43 x VDU)
    vsd = _social(
        taxable_income, vsd_rate, rule, active_months, exempt=vsd_relief, no_minimum=True
    )
    psd = _social(
        taxable_income,
        rule.psd_rate,
        rule,
        active_months,
        no_minimum=insured or psd_paid_elsewhere,
    )

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
        m_ap = _q(max(m_income - m_ded, Decimal("0")))
        m_active = start is None or (year, m) >= (start.year, start.month)
        # VSD – visada tik nuo faktinių AP (minimumo nėra)
        if vsd_relief or not m_active:
            vsd_m = Decimal("0")
        else:
            vsd_m = _q(m_ap * rule.social_base_share * vsd_rate)
        # PSD – nedraustiems kas mėn. nuo MMA; draustiems – metų gale nuo AP
        if not m_active:
            psd_m = Decimal("0")
        elif insured:
            psd_m = _q(m_ap * rule.social_base_share * rule.psd_rate)
        else:
            psd_m = _q(rule.psd_rate * rule.mma_monthly)
        monthly.append(MonthRow(m, _q(m_income), m_ap, _q(vsd_m), _q(psd_m)))

    paid_total = gpm.paid + vsd.paid + psd.paid
    remaining_total = gpm.remaining + vsd.remaining + psd.remaining
    taxes_total = _q(gpm.amount + vsd.amount + psd.amount)
    # Grynas uždarbis: 30% metu atskaitymai nominalūs -> pajamos − mokesčiai;
    # faktinių išlaidų metu atimamos ir realios išlaidos (be mokesčių įmokų,
    # kurios jau įeina į „mokesčiai" dalį)
    real_expenses = (
        expenses - paid_total
        if method == SellerProfile.DeductionsMethod.ACTUAL
        else Decimal("0")
    )
    net_earning = _q(income - real_expenses - taxes_total)

    return TaxBreakdown(
        year=year,
        months=months,
        active_months=active_months,
        income_total=income,
        expenses_total=expenses,
        deductible_total=deductible,
        deductions_method=method,
        deductions_applied=applied,
        recommended_deductions_method=recommended,
        taxable_income=taxable_income,
        net_earning=net_earning,
        gpm=gpm,
        vsd=vsd,
        psd=psd,
        total=taxes_total,
        paid_total=_q(paid_total),
        remaining_total=_q(remaining_total),
        monthly=monthly,
        warnings=warnings,
    )
