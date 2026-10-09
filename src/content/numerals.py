"""Numeral conversion shared by content labels and archive validation."""

from __future__ import annotations

CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def parse_number(value: str) -> int:
    """Read Arabic, positional Chinese, or digit-by-digit Chinese numerals."""
    if value.isdigit():
        return int(value)
    if not value or any(
        c not in CHINESE_DIGITS and c not in CHINESE_UNITS for c in value
    ):
        raise ValueError(f"unsupported Chinese numeral: {value}")
    if all(c in CHINESE_DIGITS for c in value):
        return int("".join(str(CHINESE_DIGITS[c]) for c in value))
    total = section = current = 0
    for char in value:
        if char in CHINESE_DIGITS:
            current = CHINESE_DIGITS[char]
        elif char == "万":
            total += (section + current or 1) * 10000
            section = current = 0
        else:
            section += (current or 1) * CHINESE_UNITS[char]
            current = 0
    return total + section + current


def format_chinese_numeral(value: int) -> str:
    if value < 0:
        return str(value)
    if value >= 100_000_000:
        # Positional digits remain unambiguous to parse_number at any magnitude.
        return "".join("零一二三四五六七八九"[int(c)] for c in str(value))
    if value >= 10000:
        high, low = divmod(value, 10000)
        tail = format_chinese_numeral(low) if low else ""
        if 10 <= low < 20:
            tail = "一" + tail
        if 0 < low < 1000:
            tail = "零" + tail
        return format_chinese_numeral(high) + "万" + tail
    if value == 0:
        return "零"

    digits = "零一二三四五六七八九"
    output: list[str] = []
    zero_pending = False
    remaining = value
    for place, unit in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        digit, remaining = divmod(remaining, place)
        if digit:
            if zero_pending:
                output.append("零")
            output.extend((digits[digit], unit))
            zero_pending = False
        elif output and remaining:
            zero_pending = True
    normalized = "".join(output)
    return normalized[1:] if normalized.startswith("一十") else normalized
