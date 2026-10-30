from django.http import Http404
from ninja import Router

from apps.taxes.models import TaxRule
from apps.taxes.schemas import TaxBreakdownOut, TaxRuleOut
from apps.taxes.services import compute_taxes
from apps.tenancy.api import current_tenant

router = Router(tags=["taxes"])


@router.get("/taxes/rules", response=TaxRuleOut)
def tax_rules(request, year: int | None = None):
    qs = TaxRule.objects.filter(year__lte=year) if year else TaxRule.objects.all()
    rule = qs.order_by("-year").first()
    if rule is None:
        raise Http404("Mokesčių taisyklės nerastos")
    return rule


@router.get("/taxes/summary", response=TaxBreakdownOut)
def tax_summary(request, year: int, months: int | None = None, psd_paid_elsewhere: bool = False):
    return compute_taxes(current_tenant(request), year, months, psd_paid_elsewhere)
