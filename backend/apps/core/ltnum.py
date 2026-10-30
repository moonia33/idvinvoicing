"""Lietuviški skaičių-žodžių konverteriai kasos dokumentams (KPO/PPK)."""

from decimal import Decimal

_ONES = [
    "",
    "vienas",
    "du",
    "trys",
    "keturi",
    "penki",
    "šeši",
    "septyni",
    "aštuoni",
    "devyni",
]
_TEENS = [
    "dešimt",
    "vienuolika",
    "dvylika",
    "trylika",
    "keturiolika",
    "penkiolika",
    "šešiolika",
    "septyniolika",
    "aštuoniolika",
    "devyniolika",
]
_TENS = [
    "",
    "dešimt",
    "dvidešimt",
    "trisdešimt",
    "keturiasdešimt",
    "penkiasdešimt",
    "šešiasdešimt",
    "septyniasdešimt",
    "aštuoniasdešimt",
    "devyniasdešimt",
]
_HUNDREDS = [
    "",
    "šimtas",
    "du šimtai",
    "trys šimtai",
    "keturi šimtai",
    "penki šimtai",
    "šeši šimtai",
    "septyni šimtai",
    "aštuoni šimtai",
    "devyni šimtai",
]


def _under_1000(n: int) -> str:
    parts: list[str] = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if 10 <= rest < 20:
        parts.append(_TEENS[rest - 10])
    else:
        tens, ones = divmod(rest, 10)
        if tens:
            parts.append(_TENS[tens])
        if ones:
            parts.append(_ONES[ones])
    return " ".join(parts)


def lt_int_words(n: int) -> str:
    """Sveiką skaičių 0–999999 paverčia žodžiais."""
    if not 0 <= n <= 999_999:
        raise ValueError("Palaikomi skaičiai nuo 0 iki 999999")
    if n == 0:
        return "nulis"
    thousands, rest = divmod(n, 1000)
    parts: list[str] = []
    if thousands:
        last2 = thousands % 100
        last1 = thousands % 10
        if last2 in (11, *range(12, 20)) or last1 == 0:
            form = "tūkstančių"
        elif last1 == 1:
            form = "tūkstantis"
        else:
            form = "tūkstančiai"
        parts.append(f"{_under_1000(thousands)} {form}")
    if rest:
        parts.append(_under_1000(rest))
    return " ".join(parts)


def lt_amount_words(amount: Decimal) -> str:
    """1234.56 -> 'Vienas tūkstantis du šimtai trisdešimt keturi Eur 56 ct'."""
    cents_total = int((amount * 100).quantize(Decimal("1")))
    eur, cents = divmod(cents_total, 100)
    return f"{lt_int_words(eur).capitalize()} Eur {cents:02d} ct"
