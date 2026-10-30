import pytest

from apps.taxes.models import TaxRule
from apps.taxes.services import compute_taxes
from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def paid_invoice(api_client, amount="40000.00", paid="2025-03-10"):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    inv = post_json(
        api_client,
        "/api/v1/invoices",
        {"client_id": cid, "lines": [{"description": "x", "unit_price": amount}]},
    ).json()
    post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {})
    post_json(
        api_client,
        f"/api/v1/invoices/{inv['id']}/payments",
        {"amount": amount, "paid_at": paid, "method": "bank"},
    )


def test_rules_seeded(api_client):
    resp = api_client.get("/api/v1/taxes/rules?year=2025")
    assert resp.status_code == 200
    assert resp.json()["year"] == 2025
    assert resp.json()["vsd_rate"] == "0.1252"


def test_summary_pct30(api_client, tenant):
    paid_invoice(api_client, "40000.00")
    s = api_client.get("/api/v1/taxes/summary?year=2025").json()
    assert s["income_total"] == "40000.00"
    assert s["deductions_method"] == "pct30"
    assert s["deductions_applied"] == "12000.00"
    assert s["profit"] == "28000.00"
    # GPM lengvatine formule: 28000 x (0.15 - 0.1 x (1 - 28000/35000)) = 28000 x 0.13 = 3640
    assert s["gpm"]["amount"] == "3640.00"
    # VSD/PSD bazė 90% pelno = 25200 > 12xMMA (12456)
    assert s["vsd"]["base"] == "25200.00"
    assert s["vsd"]["amount"] == "3155.04"
    assert s["psd"]["amount"] == "1758.96"
    assert s["total"] == "8554.00"


def test_summary_actual_deductions(api_client, tenant):
    api_client.put(
        "/api/v1/profile",
        {"seller_name": "Tomas IV", "deductions_method": "actual"},
        content_type="application/json",
    )
    paid_invoice(api_client, "20000.00")
    post_json(
        api_client,
        "/api/v1/ledger/entries",
        {
            "kind": "expense",
            "document_date": "2025-02-01",
            "paid_date": "2025-02-01",
            "amount_original": "3000.00",
            "deductible": True,
        },
    )
    s = api_client.get("/api/v1/taxes/summary?year=2025").json()
    assert s["deductions_applied"] == "3000.00"
    assert s["profit"] == "17000.00"


def test_min_social_base(api_client, tenant):
    paid_invoice(api_client, "3000.00")
    s = api_client.get("/api/v1/taxes/summary?year=2025").json()
    # pelnas 2100 -> bazė 1890 < 12xMMA=12456 -> minimali bazė
    assert s["vsd"]["base"] == "12456.00"
    assert "minimali" in s["vsd"]["note"]


def test_psd_exempt(api_client, tenant):
    paid_invoice(api_client, "40000.00")
    s = api_client.get("/api/v1/taxes/summary?year=2025&psd_paid_elsewhere=true").json()
    assert s["psd"]["amount"] == "0.00"


def test_rule_fallback_warns(api_client, tenant):
    TaxRule.objects.filter(year=2026).delete()
    s = compute_taxes(tenant, 2030)
    assert any("2025" in w for w in s.warnings)


def test_months_prorates_min_base(api_client, tenant):
    paid_invoice(api_client, "3000.00")
    s = api_client.get("/api/v1/taxes/summary?year=2025&months=3").json()
    # minimali bazė = 3 x 1038 = 3114 (ne 12xMMA)
    assert s["months"] == 3
    assert s["vsd"]["base"] == "3114.00"
    assert "3 x MMA" in s["vsd"]["note"]
    assert len(s["monthly"]) == 3


def test_months_limits_income_window(api_client, tenant):
    paid_invoice(api_client, "1000.00", paid="2025-01-15")
    paid_invoice(api_client, "2000.00", paid="2025-06-15")
    s = api_client.get("/api/v1/taxes/summary?year=2025&months=3").json()
    assert s["income_total"] == "1000.00"


def test_insured_elsewhere(api_client, tenant):
    api_client.put(
        "/api/v1/profile",
        {"seller_name": "Tomas IV", "insured_elsewhere": True},
        content_type="application/json",
    )
    paid_invoice(api_client, "3000.00")
    s = api_client.get("/api/v1/taxes/summary?year=2025").json()
    # VSD – be minimumo: bazė = 90% x 2100 = 1890; PSD = 0
    assert s["vsd"]["base"] == "1890.00"
    assert s["psd"]["amount"] == "0.00"


def test_tax_payments_reduce_remaining(api_client, tenant):
    paid_invoice(api_client, "3000.00")
    post_json(
        api_client,
        "/api/v1/ledger/entries",
        {
            "kind": "expense",
            "document_date": "2025-02-01",
            "paid_date": "2025-02-01",
            "amount_original": "500.00",
            "deductible": False,
            "tax_kind": "vsd",
            "tax_year": 2025,
        },
    )
    s = api_client.get("/api/v1/taxes/summary?year=2025").json()
    assert s["vsd"]["paid"] == "500.00"
    assert s["vsd"]["remaining"] == str(round(float(s["vsd"]["amount"]) - 500, 2)).ljust(0)


def test_monthly_rows_vsd_min(api_client, tenant):
    paid_invoice(api_client, "3000.00", paid="2025-03-05")
    s = api_client.get("/api/v1/taxes/summary?year=2025&months=2").json()
    m1 = s["monthly"][0]
    # Sausis: pelnas 0 -> VSD mėn. įmoka = 12.52% x MMA = 129.96, PSD = 72.45
    assert m1["vsd"] == "129.96"
    assert m1["psd"] == "72.45"
