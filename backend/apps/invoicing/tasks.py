import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.invoicing.models import Invoice, RecurringTemplate
from apps.invoicing.services import add_months, issue_invoice
from apps.mailer.services import queue_invoice_email

logger = logging.getLogger(__name__)

STEP_MONTHS: dict[str, int] = {
    RecurringTemplate.Frequency.MONTHLY: 1,
    RecurringTemplate.Frequency.QUARTERLY: 3,
    RecurringTemplate.Frequency.YEARLY: 12,
}


def generate_recurring_invoices() -> dict:
    """Generuoja sąskaitas iš aktyvių recurring šablonų; kviečiama iš qcluster kasdien."""
    created = sent = 0
    today = timezone.localdate()
    templates = (
        RecurringTemplate.objects.filter(active=True, next_run_date__lte=today)
        .select_related("client", "tenant")
        .prefetch_related("lines")
    )

    for tpl in templates:
        with transaction.atomic():
            invoice = Invoice.objects.create(
                tenant=tpl.tenant,
                client=tpl.client,
                series=tpl.series,
                notes=tpl.notes,
                due_date=today + timedelta(days=14),
            )
            for line in tpl.lines.all():
                invoice.lines.create(
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    order=line.order,
                )
            invoice.recalc_total()
            issue_invoice(invoice, today)
            created += 1

            recipient = tpl.email_to or tpl.client.email
            if tpl.auto_send and recipient:
                queue_invoice_email(invoice, recipient)
                sent += 1

            next_run = add_months(tpl.next_run_date, STEP_MONTHS[tpl.frequency])
            while next_run <= today:
                next_run = add_months(next_run, STEP_MONTHS[tpl.frequency])
            tpl.next_run_date = next_run
            if tpl.end_date and next_run > tpl.end_date:
                tpl.active = False
            tpl.save()
            logger.info(
                "Recurring invoice %s generated for template %s", invoice.full_number, tpl.id
            )

    return {"created": created, "queued_emails": sent}
