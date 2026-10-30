from ninja import NinjaAPI
from ninja.security import django_auth

from apps.invoicing.api import router as invoicing_router
from apps.ledger.api import router as ledger_router
from apps.purchases.api import router as purchases_router
from apps.mailer.api import router as mailer_router
from apps.reports.api import router as reports_router
from apps.taxes.api import router as taxes_router
from apps.tenancy.api import router as tenancy_router

api = NinjaAPI(
    title="IDV Apskaita API",
    urls_namespace="api",
    auth=django_auth,
)

api.add_router("", tenancy_router)
api.add_router("", invoicing_router)
api.add_router("", purchases_router)
api.add_router("", ledger_router)
api.add_router("", mailer_router)
api.add_router("", taxes_router)
api.add_router("", reports_router)


@api.get("/health", auth=None, tags=["meta"])
def health(request):
    return {"status": "ok"}
