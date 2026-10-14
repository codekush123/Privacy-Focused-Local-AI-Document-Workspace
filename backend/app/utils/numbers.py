"""Read numbers written the English or the Finnish way.

"1 148", "184,6", "1 148,5" (Finnish), "1,148", "1,148.5" (English) and
"1.148,5" (German) are all ordinary ways to write a number, and a table
exported in Finland uses them. Read naively, "184,6" is text that cannot be
summed and "1,148" becomes 1.148.

One case cannot be decided from the string alone: a single comma followed by
exactly three digits ("1,148") is 1148 in English and 1.148 in Finnish. The
convention of the whole column decides it (``infer_decimal_comma``); when there
is no evidence either way the value is left as text rather than guessed.
"""
from __future__ import annotations

import re

_SPACE = r"[ \u00a0\u2009\u202f]"  # space, no-break space, thin spaces
_SPACE_GROUPED = re.compile(rf"(\d{{1,3}}(?:{_SPACE}\d{{3}})+)(?:([.,])(\d+))?")
_PLAIN = re.compile(r"\d+(?:[.,]\d+)*")
_GROUPED = {",": re.compile(r"\d{1,3}(?:,\d{3})+"), ".": re.compile(r"\d{1,3}(?:\.\d{3})+")}

# Evidence for a column's convention, one value at a time.
_COMMA_DECIMAL = [
    re.compile(r"\d,\d{1,2}$"),  # 184,6 / 12,50
    re.compile(r"\d,\d{4,}$"),  # 0,1234
    re.compile(r"\d\.\d{3},\d+$"),  # 1.148,5
    re.compile(r"^\d{1,3}(?:\.\d{3}){2,}$"),  # 1.148.000
]
_DOT_DECIMAL = [
    re.compile(r"\d\.\d{1,2}$"),  # 184.6 / 12.50
    re.compile(r"\d\.\d{4,}$"),  # 0.1234
    re.compile(r"\d,\d{3}\.\d+$"),  # 1,148.5
    re.compile(r"^\d{1,3}(?:,\d{3}){2,}$"),  # 1,148,000
]


def parse_number(text: object, decimal_comma: bool | None = None) -> int | float | None:
    """The value of a written number, or None when it is not one or is ambiguous.

    ``decimal_comma``: True when the comma is the decimal mark (Finnish,
    German), False when it is the dot (English), None when unknown. A trailing
    percent sign is dropped ("45 %" -> 45), a leading + or - (or −) kept.
    Digits with a leading zero ("007", the postcode "00100", "040 123 456")
    are identifiers, not numbers.
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.endswith("%"):
        s = s[:-1].rstrip()
    sign = ""
    if s[:1] in ("+", "-", "−"):
        sign = "" if s[0] == "+" else "-"
        s = s[1:].lstrip()
    if len(s) > 1 and s[0] == "0" and s[1].isdigit():
        return None

    grouped = _SPACE_GROUPED.fullmatch(s)
    if grouped:  # "1 148", "184 600 000", "1 148,5": spaces group thousands
        whole = re.sub(_SPACE, "", grouped.group(1))
        return _value(sign, whole, grouped.group(3) or "")
    if not _PLAIN.fullmatch(s):
        return None

    commas, dots = s.count(","), s.count(".")
    if not commas and not dots:
        return _value(sign, s, "")
    if commas and dots:  # "1,148.5" / "1.148,5": the last mark is the decimal mark
        mark = "," if s.rfind(",") > s.rfind(".") else "."
        other = "." if mark == "," else ","
        whole, frac = s.rsplit(mark, 1)
        if mark in whole or not _GROUPED[other].fullmatch(whole):
            return None
        return _value(sign, whole.replace(other, ""), frac)
    mark = "," if commas else "."
    if commas + dots > 1:  # "1,148,000" / "1.148.000": thousands groups only
        return _value(sign, s.replace(mark, ""), "") if _GROUPED[mark].fullmatch(s) else None

    whole, frac = s.split(mark)
    if len(frac) != 3 or len(whole) > 3 or whole == "0":
        return _value(sign, whole, frac)  # cannot be a thousands group: a decimal mark
    # One mark followed by three digits: thousands or decimals, by convention.
    if mark == ",":
        if decimal_comma is None:
            return None
        return _value(sign, whole, frac) if decimal_comma else _value(sign, whole + frac, "")
    return _value(sign, whole + frac, "") if decimal_comma else _value(sign, whole, frac)


def _value(sign: str, whole: str, frac: str) -> int | float:
    return float(f"{sign}{whole}.{frac}") if frac else int(f"{sign}{whole}")


def infer_decimal_comma(values: list[object]) -> bool | None:
    """True / False when the values show which mark is the decimal mark, else None."""
    comma = dot = False
    for v in values:
        s = re.sub(_SPACE, " ", str(v).strip().rstrip("%").strip())
        comma = comma or any(p.search(s) for p in _COMMA_DECIMAL)
        dot = dot or any(p.search(s) for p in _DOT_DECIMAL)
    return comma if comma != dot else None
