"""ISO 20022 camt.053 (banko sąskaitos išrašo) skaitytuvas.

Palaikomos camt.053.001.02–.13 versijos (Citadele, Paysera, Swedbank, SEB, Luminor ir kt.).
XML skaitomas per defusedxml (be DTD/išorinių esybių)."""

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ENTRIES = 5000
CAMT053_NS_PREFIX = "urn:iso:std:iso:20022:tech:xsd:camt.053."


class CamtError(ValueError):
    pass


@dataclass
class Entry:
    direction: str  # in | out
    date: dt.date
    amount: Decimal
    currency: str
    external_id: str
    counterparty_name: str = ""
    counterparty_iban: str = ""
    counterparty_code: str = ""
    reference: str = ""
    method: str = "bank"
    bank_code: str = ""  # Domn/Fmly/SubFmly, pvz. PMNT/CCRD/POSD
    own_transfer: bool = False


@dataclass
class Statement:
    account_iban: str
    currency: str
    bank_name: str = ""
    owner_name: str = ""
    owner_code: str = ""
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    entries: list[Entry] = field(default_factory=list)
    skipped: int = 0  # ne BOOK būsenos (laukiančios) operacijos


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: Element | None, *path: str) -> Element | None:
    """Randa vaiką pagal kelią, ignoruodamas namespace."""
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == name), None)
    return el


def _text(el: Element | None, *path: str) -> str:
    found = _child(el, *path)
    return (found.text or "").strip() if found is not None else ""


def _date(el: Element | None) -> dt.date | None:
    raw = _text(el, "Dt") or _text(el, "DtTm")
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _party(tx: Element | None, role: str) -> tuple[str, str, str]:
    """(pavadinimas, IBAN arba sąskaitos ID, įmonės/asmens kodas) – Dbtr arba Cdtr."""
    parties = _child(tx, "RltdPties")
    party = _child(parties, role)
    # camt.053.001.08+: <Dbtr><Pty><Nm>…
    if _child(party, "Pty") is not None:
        party = _child(party, "Pty")
    name = _text(party, "Nm")
    acct = _child(parties, f"{role}Acct", "Id")
    iban = _text(acct, "IBAN") or _text(acct, "Othr", "Id")
    code = _text(party, "Id", "OrgId", "Othr", "Id") or _text(party, "Id", "PrvtId", "Othr", "Id")
    return name, iban.replace(" ", "").upper(), code


def _reference(tx: Element | None) -> str:
    rmt = _child(tx, "RmtInf")
    if rmt is None:
        return ""
    parts = [(c.text or "").strip() for c in rmt if _local(c.tag) == "Ustrd"]
    for strd in (c for c in rmt if _local(c.tag) == "Strd"):
        ref = _text(strd, "CdtrRefInf", "Ref")
        if ref:
            parts.append(ref)
    return " ".join(p for p in parts if p)[:500]


def _method(domain: str, family: str, sub: str) -> str:
    if family == "CCRD" or sub in ("POSD", "CWDL"):
        return "card"
    return "bank"


def parse(data: bytes) -> list[Statement]:
    if len(data) > MAX_FILE_SIZE:
        raise CamtError("Failas per didelis (daugiausia 10 MB)")
    try:
        root = SafeET.fromstring(data, forbid_dtd=True)
    except DefusedXmlException as e:
        raise CamtError("Netinkamas XML failas (draudžiamos DTD/esybės)") from e
    except SafeET.ParseError as e:
        raise CamtError("Netinkamas XML failas") from e
    if _local(root.tag) != "Document" or not root.tag.startswith("{" + CAMT053_NS_PREFIX):
        raise CamtError("Tai ne camt.053 banko išrašas")
    report = _child(root, "BkToCstmrStmt")
    if report is None:
        raise CamtError("Išraše nėra BkToCstmrStmt")

    statements: list[Statement] = []
    total = 0
    for stmt_el in (c for c in report if _local(c.tag) == "Stmt"):
        acct = _child(stmt_el, "Acct")
        iban = (_text(acct, "Id", "IBAN") or _text(acct, "Id", "Othr", "Id")).replace(" ", "")
        if not iban:
            raise CamtError("Išraše nenurodyta sąskaita")
        stmt = Statement(
            account_iban=iban.upper(),
            currency=_text(acct, "Ccy"),
            bank_name=_text(acct, "Svcr", "FinInstnId", "Nm"),
            owner_name=_text(acct, "Ownr", "Nm"),
            owner_code=_text(acct, "Ownr", "Id", "OrgId", "Othr", "Id")
            or _text(acct, "Ownr", "Id", "PrvtId", "Othr", "Id"),
        )
        period = _child(stmt_el, "FrToDt")
        if period is not None:
            stmt.period_from = _parse_iso(_text(period, "FrDtTm") or _text(period, "FrDt"))
            stmt.period_to = _parse_iso(_text(period, "ToDtTm") or _text(period, "ToDt"))
        seen: dict[str, int] = {}
        for n in (c for c in stmt_el if _local(c.tag) == "Ntry"):
            total += 1
            if total > MAX_ENTRIES:
                raise CamtError(f"Per daug operacijų (daugiausia {MAX_ENTRIES})")
            entries = _entries(n, stmt, seen)
            if entries:
                stmt.entries.extend(entries)
            else:
                stmt.skipped += 1
        statements.append(stmt)
    if not statements:
        raise CamtError("Išraše nėra sąskaitų")
    return statements


def _parse_iso(raw: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(raw[:10]) if raw else None
    except ValueError:
        return None


def _amount(el: Element | None) -> Decimal | None:
    try:
        value = Decimal(_text(el, "Amt"))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _entries(n: Element, stmt: Statement, seen: dict[str, int]) -> list[Entry]:
    """Viena išrašo eilutė (Ntry). Paketinis mokėjimas (keli TxDtls su sumomis) išskaidomas."""
    status = _text(n, "Sts") or _text(n, "Sts", "Cd")
    if status and status != "BOOK":
        return []
    amount = _amount(n)
    if amount is None:
        return []
    amt_el = _child(n, "Amt")
    currency = (amt_el.get("Ccy") if amt_el is not None else "") or stmt.currency
    indicator = _text(n, "CdtDbtInd")
    if indicator not in ("CRDT", "DBIT"):
        return []
    booked = _date(_child(n, "BookgDt")) or _date(_child(n, "ValDt"))
    if booked is None:
        return []
    txs = [
        tx
        for dtls in n
        if _local(dtls.tag) == "NtryDtls"
        for tx in dtls
        if _local(tx.tag) == "TxDtls"
    ]
    parts: list[tuple[Element | None, Decimal]] = [(txs[0] if txs else None, amount)]
    if len(txs) > 1:
        tx_amounts = [_amount(_child(tx, "AmtDtls", "TxAmt")) or _amount(tx) for tx in txs]
        if all(tx_amounts) and sum(a for a in tx_amounts if a) == amount:
            parts = [(tx, a) for tx, a in zip(txs, tx_amounts, strict=True) if a]
    base_ref = "|".join(p for p in (_text(n, "NtryRef"), _text(n, "AcctSvcrRef")) if p)
    result = []
    for idx, (tx, part_amount) in enumerate(parts):
        ref = base_ref or _text(tx, "Refs", "AcctSvcrRef")
        if len(parts) > 1 and not ref:
            ref = _text(tx, "Refs", "AcctSvcrRef")
        entry = _entry_from_tx(n, tx, stmt, indicator, booked, part_amount, currency, ref)
        if len(parts) > 1:
            entry.external_id = f"{entry.external_id}/{idx + 1}"
        # Identiškos operacijos be ID tame pačiame išraše – numeruojamos.
        seen[entry.external_id] = seen.get(entry.external_id, 0) + 1
        if seen[entry.external_id] > 1:
            entry.external_id = f"{entry.external_id}#{seen[entry.external_id]}"
        entry.external_id = entry.external_id[:100]
        result.append(entry)
    return result


def _entry_from_tx(
    n: Element,
    tx: Element | None,
    stmt: Statement,
    indicator: str,
    booked: dt.date,
    amount: Decimal,
    currency: str,
    ref: str,
) -> Entry:
    domain = _text(n, "BkTxCd", "Domn", "Cd")
    family = _text(n, "BkTxCd", "Domn", "Fmly", "Cd")
    sub = _text(n, "BkTxCd", "Domn", "Fmly", "SubFmlyCd")
    incoming = indicator == "CRDT"
    name, iban, code = _party(tx, "Dbtr" if incoming else "Cdtr")
    reference = _reference(tx)
    ext = "|".join(p for p in (ref, _text(tx, "Refs", "TxId")) if p)
    if not ext:
        digest = hashlib.sha256(
            f"{booked}|{indicator}|{amount}|{currency}|{name}|{iban}|{reference}".encode()
        ).hexdigest()[:32]
        ext = f"h:{digest}"
    own = (
        domain == "FORX"
        or (bool(iban) and iban == stmt.account_iban)
        or (bool(code) and bool(stmt.owner_code) and code == stmt.owner_code)
    )
    return Entry(
        direction="in" if incoming else "out",
        date=booked,
        amount=amount.quantize(Decimal("0.01")),
        currency=currency,
        external_id=ext,
        counterparty_name=name[:200],
        counterparty_iban=iban[:34],
        counterparty_code=code[:50],
        reference=reference,
        method=_method(domain, family, sub),
        bank_code="/".join(p for p in (domain, family, sub) if p),
        own_transfer=own,
    )
