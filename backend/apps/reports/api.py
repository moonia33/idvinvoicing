from django.http import HttpResponse
from ninja import Router

from apps.reports.services import journal_workbook, taxes_workbook
from apps.tenancy.api import current_tenant

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = Router(tags=["reports"])


def _xlsx(content: bytes, filename: str) -> HttpResponse:
    resp = HttpResponse(content, content_type=XLSX_MIME)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@router.get("/reports/journal.xlsx", response=None)
def journal_xlsx(request, year: int, month: int | None = None):
    return _xlsx(
        journal_workbook(current_tenant(request), year, month),
        f"zurnalas_{year}{f'_{month:02d}' if month else ''}.xlsx",
    )


@router.get("/reports/taxes.xlsx", response=None)
def taxes_xlsx(request, year: int, psd_paid_elsewhere: bool = False):
    return _xlsx(
        taxes_workbook(current_tenant(request), year, psd_paid_elsewhere),
        f"mokesciai_{year}.xlsx",
    )
