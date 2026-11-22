"""Türkçe sayı ve zaman biçimlendirme."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def number(value: Decimal | float | int, digits: int = 0) -> str:
    """1234567.5 -> '1.234.567,50' (Türkçe ayraçlar)."""
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def credits(value: Decimal | float | int) -> str:
    v = float(value)
    return number(v, 0 if abs(v) >= 1000 else 2 if abs(v) < 10 else 1)


def compact(value: Decimal | float | int) -> str:
    v = float(value)
    if abs(v) >= 1_000_000:
        return number(v / 1_000_000, 1) + " Mn"
    if abs(v) >= 10_000:
        return number(v / 1000, 1) + " B"
    if abs(v) < 10 and v != int(v):
        return number(v, 1)
    return number(v, 0)


def percent(ratio: float, digits: int = 0) -> str:
    return "%" + number(ratio * 100, digits)


def clock(dt: datetime | None, seconds: bool = True) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%H:%M:%S" if seconds else "%H:%M")


def when(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d.%m %H:%M")


def ago(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    seconds = int((datetime.now() - dt).total_seconds())
    if seconds < 60:
        return "az önce"
    if seconds < 3600:
        return f"{seconds // 60} dk önce"
    if seconds < 86400:
        return f"{seconds // 3600} sa önce"
    return dt.strftime("%d.%m.%Y")


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "kapalı"
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600} sa {s % 3600 // 60:02d} dk"
    return f"{s // 60:02d}:{s % 60:02d}"
