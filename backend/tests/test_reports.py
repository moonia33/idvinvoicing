from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.conftest import post_json

pytestmark = pytest.mark.django_db

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_journal_xlsx(api_client):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    inv = post_json(
        api_client,
        "/api/v1/invoices",
        {"client_id": cid, "lines": [{"description": "x", "unit_price": "100.00"}]},
    ).json()
    post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {})
    post_json(
        api_client,
        f"/api/v1/invoices/{inv['id']}/payments",
        {"amount": "100.00", "paid_at": "2025-01-15", "method": "bank"},
    )

    resp = api_client.get("/api/v1/reports/journal.xlsx?year=2025&month=1")
    assert resp.status_code == 200
    assert resp["Content-Type"] == XLSX_MIME
    wb = load_workbook(BytesIO(resp.content))
    ws = wb.active
    assert ws.title == "Žurnalas"
    assert ws["A1"].value == "Data"
    assert ws["E2"].value == 100.0


def test_journal_xlsx_bad_month(api_client):
    resp = api_client.get("/api/v1/ledger/journal?year=2025&month=13")
    assert resp.status_code == 400


def test_taxes_xlsx(api_client):
    resp = api_client.get("/api/v1/reports/taxes.xlsx?year=2025")
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.content))
    assert wb.active["A1"].value == "Mokestinė suvestinė 2025 m."
