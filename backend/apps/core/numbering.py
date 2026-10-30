from django.db import transaction

from apps.core.models import DocumentSequence
from apps.tenancy.models import Tenant


def next_document_number(tenant: Tenant, kind: str, series: str, year: int) -> int:
    """Atomiškai išduoda sekantį dokumento numerį (row lock – nėra dublikatų)."""
    with transaction.atomic():
        seq = DocumentSequence.objects.select_for_update().get_or_create(
            tenant=tenant, kind=kind, series=series, year=year
        )[0]
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        return seq.last_number
