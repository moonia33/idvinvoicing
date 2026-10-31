from io import BytesIO
from typing import cast

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from apps.ledger.services import journal_rows, journal_summary
from apps.taxes.services import compute_taxes
from apps.tenancy.models import Tenant

BOLD = Font(bold=True)


def _sheet(wb: Workbook) -> Worksheet:
    return cast(Worksheet, wb.active)


def _autosize(ws):
    for col in ws.columns:
        width = max(len(str(c.value)) for c in col if c.value is not None)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)


def journal_workbook(tenant: Tenant, year: int, month: int | None = None) -> bytes:
    wb = Workbook()
    ws = _sheet(wb)
    ws.title = "Žurnalas"
    ws.append(["Data", "Tipas", "Aprašymas", "Kontragentas", "Suma EUR", "Atskaitymai", "Šaltinis"])
    for c in ws[1]:
        c.font = BOLD

    months = [month] if month else range(1, 13)
    for m in months:
        for r in journal_rows(tenant, year, m):
            ws.append(
                [
                    str(r.date),
                    "Pajamos" if r.kind == "income" else "Išlaidos",
                    r.description,
                    r.counterparty,
                    float(r.amount),
                    "Taip" if r.deductible else "",
                    r.source,
                ]
            )

    s = journal_summary([r for m in months for r in journal_rows(tenant, year, m)])
    ws.append([])
    for label, value in [
        ("Pajamos iš viso", s["income_total"]),
        ("Išlaidos iš viso", s["expense_total"]),
        ("Leidžiami atskaitymai", s["deductible_total"]),
        ("Grynasis rezultatas", s["net"]),
    ]:
        ws.append(["", "", "", label, float(value)])
        ws[ws.max_row][3].font = BOLD

    _autosize(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def taxes_workbook(tenant: Tenant, year: int, psd_paid_elsewhere: bool = False) -> bytes:
    t = compute_taxes(tenant, year, psd_paid_elsewhere)
    wb = Workbook()
    ws = _sheet(wb)
    ws.title = "Mokesčiai"
    ws.append([f"Mokestinė suvestinė {year} m.", "", ""])
    ws[1][0].font = BOLD
    rows = [
        ("Pajamos iš viso", t.income_total),
        ("Išlaidos iš viso", t.expenses_total),
        ("Leidžiami atskaitymai (žurnalas)", t.deductible_total),
        (
            f"Pritaikyti atskaitymai ({t.deductions_method})",
            t.deductions_applied,
        ),
        ("Apmokestinamosios pajamos (AP)", t.taxable_income),
        ("GPM", t.gpm.amount, f"{t.gpm.rate} – {t.gpm.note}"),
        ("VSD", t.vsd.amount, f"bazė {t.vsd.base} – {t.vsd.note}"),
        ("PSD", t.psd.amount, f"bazė {t.psd.base} – {t.psd.note}"),
        ("Iš viso mokesčių", t.total),
        ("Grynas uždarbis (pajamos − mokesčiai)", t.net_earning),
    ]
    for row in rows:
        ws.append([row[0], float(row[1]), row[2] if len(row) > 2 else ""])
    for w in t.warnings:
        ws.append([w])
    ws[ws.max_row - len(t.warnings) - 1][0].font = BOLD

    _autosize(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
