"""Banko operacijų susiejimo pasiūlymai ir automatinis sudengimas (3 etapas).

Automatiškai sudengiama TIK tada, kai paskirtyje yra vienintelio atviro dokumento numeris
ir suma lygi jo likučiui. Visa kita – tik pasiūlymai, kuriuos patvirtina naudotojas."""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.invoicing.models import Counterparty, Invoice
from apps.payments.models import MoneyTransfer
from apps.payments.services import (
    OPEN_INVOICE,
    OPEN_PURCHASE,
    _norm_name,
    allocate,
    invoice_remaining,
    purchase_remaining,
)
from apps.purchases.models import Purchase

MIN_SCORE = 30


def _compact(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", text.upper())


def number_in_text(number: str, text: str) -> bool:
    """Dokumento numeris tekste kaip atskiras žodis (skyrybos ženklai tarp simbolių leidžiami):
    „SF-2026-0001“ randamas „sf 2026/0001“, bet „1234“ nerandamas „12345“."""
    if not number:
        return False
    body = r"[^0-9A-Z]*".join(re.escape(ch) for ch in number)
    return re.search(rf"(?<![0-9A-Z]){body}(?![0-9A-Z])", text.upper()) is not None


@dataclass
class Doc:
    kind: str  # invoice | purchase
    id: int
    label: str
    number: str  # normalizuotas numeris paieškai paskirtyje
    counterparty: Counterparty
    currency: str
    remaining: Decimal
    date: object


@dataclass
class Suggestion:
    doc: Doc
    score: int
    reasons: list[str] = field(default_factory=list)
    number_match: bool = False
    amount_match: bool = False


def open_docs(tenant, direction: str) -> list[Doc]:
    docs: list[Doc] = []
    if direction == MoneyTransfer.Direction.IN:
        for inv in (
            Invoice.objects.filter(tenant=tenant, status__in=OPEN_INVOICE)
            .select_related("client")
            .prefetch_related("payments")
        ):
            rem = invoice_remaining(inv)
            if rem > 0 and inv.full_number:
                docs.append(
                    Doc(
                        "invoice",
                        inv.id,
                        inv.full_number,
                        _compact(inv.full_number),
                        inv.client,
                        inv.currency,
                        rem,
                        inv.issue_date,
                    )
                )
    else:
        for pur in (
            Purchase.objects.filter(tenant=tenant, status__in=OPEN_PURCHASE)
            .select_related("supplier")
            .prefetch_related("payments")
        ):
            rem = purchase_remaining(pur)
            if rem > 0:
                number = _compact(pur.doc_number)
                docs.append(
                    Doc(
                        "purchase",
                        pur.id,
                        pur.doc_number or f"Pirkinys #{pur.pk}",
                        number if len(number) >= 4 else "",
                        pur.supplier,
                        pur.currency,
                        rem,
                        pur.document_date,
                    )
                )
    return docs


def score(transfer: MoneyTransfer, doc: Doc) -> Suggestion:
    s = Suggestion(doc, 0)
    if doc.currency != transfer.currency:
        return s
    if number_in_text(doc.number, f"{transfer.reference} {transfer.doc_number}"):
        s.score += 60
        s.number_match = True
        s.reasons.append("numeris paskirtyje")
    if transfer.amount == doc.remaining:
        s.score += 30
        s.amount_match = True
        s.reasons.append("suma = likutis")
    elif transfer.unallocated == doc.remaining:
        s.score += 25
        s.amount_match = True
        s.reasons.append("nesudengta suma = likutis")
    cp = doc.counterparty
    if transfer.counterparty_id and transfer.counterparty_id == cp.id:
        s.score += 25
        s.reasons.append("kontragentas")
    elif transfer.counterparty_iban and cp.iban and transfer.counterparty_iban == cp.iban:
        s.score += 25
        s.reasons.append("IBAN")
    elif transfer.counterparty_name:
        a, b = _norm_name(transfer.counterparty_name), _norm_name(cp.name)
        if a and a == b:
            s.score += 20
            s.reasons.append("pavadinimas")
        elif a and b and set(a.split()) & set(b.split()):
            s.score += 10
            s.reasons.append("panašus pavadinimas")
    return s


def suggest(transfer: MoneyTransfer, docs: list[Doc], limit: int = 3) -> list[Suggestion]:
    if transfer.ignored or transfer.ledger_entry_id or transfer.unallocated <= 0:
        return []
    found = [score(transfer, d) for d in docs]
    found = [s for s in found if s.score >= MIN_SCORE]
    found.sort(key=lambda s: (-s.score, str(s.doc.date or "")))
    return found[:limit]


def auto_target(transfer: MoneyTransfer, docs: list[Doc]) -> Doc | None:
    """Vienintelis dokumentas, kurio numeris yra paskirtyje ir likutis = suma."""
    if transfer.ignored or transfer.allocated_total > 0:
        return None
    hits = [s for s in (score(transfer, d) for d in docs) if s.number_match]
    if len(hits) == 1 and transfer.amount == hits[0].doc.remaining:
        return hits[0].doc
    return None


def remember_counterparty(transfer: MoneyTransfer, counterparty: Counterparty) -> None:
    """Patvirtinus sudengimą: mokėjimui priskiriamas kontragentas, jam įsimenamas IBAN."""
    if transfer.counterparty_id is None:
        MoneyTransfer.objects.filter(pk=transfer.pk).update(counterparty=counterparty)
        transfer.counterparty = counterparty
    iban = transfer.counterparty_iban
    # IBAN įsimenamas tik jei mokėtojas – tas pats asmuo (ne trečioji šalis).
    payer, owner = _norm_name(transfer.counterparty_name), _norm_name(counterparty.name)
    same_party = bool(payer) and (payer == owner or set(payer.split()) == set(owner.split()))
    if iban and same_party and not counterparty.iban and len(iban) >= 15 and iban[:2].isalpha():
        Counterparty.objects.filter(pk=counterparty.pk, iban="").update(iban=iban)
        counterparty.iban = iban


def auto_allocate(tenant, transfers) -> int:
    count = 0
    cache: dict[str, list[Doc]] = {}
    for t in transfers:
        docs = cache.setdefault(t.direction, open_docs(tenant, t.direction))
        doc = auto_target(t, docs)
        if doc is None:
            continue
        if doc.kind == "invoice":
            allocate(t, t.amount, invoice_id=doc.id)
        else:
            allocate(t, t.amount, purchase_id=doc.id)
        remember_counterparty(t, doc.counterparty)
        docs.remove(doc)
        count += 1
    return count


TAX_PATTERNS = (
    (re.compile(r"\bSODRA\b|SOCIALINIO DRAUDIMO|\bVSDF", re.I), "vsd"),
    (re.compile(r"\bVMI\b|MOKES[CČ]I[UŲ] INSPEKCIJA", re.I), "gpm"),
)
FEE_PATTERN = re.compile(r"KOMISIN|COMMISSION|MOKESTIS U[ZŽ]|APTARNAVIMO|\bFEE\b", re.I)


def ledger_hint(transfer: MoneyTransfer) -> dict | None:
    """Pasiūlymas žurnalo įrašui operacijai be dokumento (Sodra, VMI, banko mokesčiai)."""
    if transfer.direction != MoneyTransfer.Direction.OUT or transfer.ignored:
        return None
    if transfer.allocated_total > 0:
        return None
    text = f"{transfer.counterparty_name} {transfer.reference}"
    for pattern, kind in TAX_PATTERNS:
        if pattern.search(text):
            if kind == "vsd" and re.search(r"\bPSD\b|SVEIKATOS", transfer.reference, re.I):
                kind = "psd"
            year = transfer.date.year - 1 if kind == "gpm" else transfer.date.year
            return {
                "kind": "expense",
                "tax_kind": kind,
                "tax_year": year,
                "description": f"{kind.upper()} įmoka",
                "deductible": kind != "gpm",
                "category_name": "",
            }
    is_fee = bool(re.search(r"/(CHRG|FEES|NTAV)$", transfer.bank_code))
    if is_fee or FEE_PATTERN.search(text):
        return {
            "kind": "expense",
            "tax_kind": "",
            "tax_year": None,
            "description": "Banko mokestis",
            "deductible": True,
            "category_name": "Banko mokesčiai",
        }
    return None
