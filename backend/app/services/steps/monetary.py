"""Amounts for Paperless monetary custom fields.

Paperless stores a monetary value as a plain number with at most two decimals
or as a three-letter currency code followed by one, e.g. "EUR104.99". Models
answer the way invoices are written ("104,99 €", "1.234,56 EUR"), so the value
is rewritten here, or refused when it cannot be read as one amount.
"""

import re
from decimal import Decimal
from typing import Any, Optional

# Current ISO 4217 codes plus a few recently replaced ones that still turn up
# on older invoices. Paperless only checks for three capitals, so anything
# else next to a number ("Mio", "Stk", "net") must not pass as a currency.
_ISO_4217 = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB
    BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC
    CUP CVE CZK DEM DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD
    GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS
    KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT
    MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK
    PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS
    SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN
    UYI UYU UYW UZS VED VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG ZWL
    """.split()
)
# Written in lower case these are still plainly currencies; other codes only
# count in capitals, so "all 100", "top 5" or "12 Sek" stay words.
_PLAIN_IN_LOWER_CASE = frozenset("EUR USD GBP CHF JPY CAD AUD NOK DKK PLN CZK HUF".split())
_CURRENCIES = {
    "€": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
    "US$": "USD",
    "FR": "CHF",
    "FR.": "CHF",
    "SFR": "CHF",
    "SFR.": "CHF",
    "DM": "DEM",
}
# A bare $, £ or ¥ is the field's own currency when that one is written so,
# otherwise the best-known one.
_SIGNS = {
    "$": ("USD", frozenset(
        "USD CAD AUD NZD HKD SGD TWD MXN ARS CLP COP CUP DOP UYU BSD BBD BZD BMD "
        "BND FJD GYD JMD KYD LRD NAD SBD SRD TTD XCD".split()
    )),
    "£": ("GBP", frozenset("GBP EGP GIP FKP SHP SSP SYP LBP".split())),
    "¥": ("JPY", frozenset("JPY CNY".split())),
}
_SPACES = "    "
_SEPARATOR = re.compile(f"[.,'’{_SPACES}]")
_NUMBER = re.compile(f"\\d+(?:[.,'’{_SPACES}]\\d+)*")
# "104,-" and "104,--" are whole amounts; the separator stays to show which
# one marks the decimals.
_WHOLE = re.compile(r"(\d)([.,])[-–—]+(?![\d\-–—])")
_MINUS = ("-", "−")
# Paperless keeps twelve digits, two of them after the point.
_MAX_INTEGER_DIGITS = 10


def format_monetary(value: Any, default_currency: Optional[str] = None) -> Optional[str]:
    """The value in a form Paperless accepts for a monetary field, or None.

    A value without a currency takes the field's default currency when it has
    one. None means the value is not one readable amount: several numbers,
    words around it, or a separator that could mean thousands or decimals.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = _WHOLE.sub(r"\1\g<2>00", str(value).strip())

    numbers = _NUMBER.findall(text)
    if len(numbers) != 1:
        return None
    amount = _parse_number(numbers[0])
    if amount is None:
        return None

    rest = text.replace(numbers[0], " ", 1)
    minus = sum(rest.count(sign) for sign in _MINUS)
    if minus + rest.count("+") > 1:
        return None
    for sign in (*_MINUS, "+"):
        rest = rest.replace(sign, "")

    default = (default_currency or "").strip().upper()
    if default not in _ISO_4217:
        default = ""
    code = _currency(rest, default)
    if code is None:
        return None

    number = str(amount.quantize(Decimal("0.01")))
    if minus and amount:
        number = "-" + number
    return (code or default) + number


def _parse_number(token: str) -> Optional[Decimal]:
    """Digits with thousands and decimal separators in either convention."""
    groups = _SEPARATOR.split(token)
    separators = [
        " " if s in _SPACES else "'" if s in "'’" else s
        for s in _SEPARATOR.findall(token)
    ]
    fraction = "0"
    if separators and separators[-1] in ".," and len(groups[-1]) in (1, 2):
        fraction = groups.pop()
        point = separators.pop()
        if point in separators:
            return None
    elif len(separators) == 1 and separators[0] in ".," and len(groups[-1]) == 3:
        # "1.679" is a thousand or three decimals; there is no telling which.
        return None
    if separators and (
        len(set(separators)) > 1
        or not 1 <= len(groups[0]) <= 3
        or any(len(group) != 3 for group in groups[1:])
    ):
        return None
    integer = "".join(groups).lstrip("0") or "0"
    if len(integer) > _MAX_INTEGER_DIGITS:
        return None
    return Decimal(f"{integer}.{fraction}")


def _currency(rest: str, default: str) -> Optional[str]:
    """The ISO code written next to the amount, "" for none, None if unreadable."""
    token = re.sub(r"\s+", "", rest)
    if not token:
        return ""
    upper = token.upper()
    if upper in _SIGNS:
        usual, written_so = _SIGNS[upper]
        return default if default in written_so else usual
    if upper in _CURRENCIES:
        return _CURRENCIES[upper]
    if upper in _ISO_4217 and (token.isupper() or upper in _PLAIN_IN_LOWER_CASE):
        return upper
    return None
