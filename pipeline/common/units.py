"""Deterministic transforms only. Nothing here depends on the peer group.

The line this file defends: percentiles, weights and composite scores are NOT
computed before the database. They are what the sliders move, and percentiles
are sector-relative, so they go stale the moment a filter changes. Scoring runs
client-side, on the normalised matrix, in the browser.

What belongs here: unit harmonisation, currency, fiscal-year alignment.
"""

from __future__ import annotations

from datetime import date

# Emissions -> tCO2e
_TO_TCO2E = {
    "tco2e": 1.0, "t": 1.0, "tonnes": 1.0, "metric tons": 1.0, "mt": 1.0,
    "ktco2e": 1e3, "kt": 1e3,
    "mtco2e": 1e6, "million tonnes": 1e6,
    "kgco2e": 1e-3, "kg": 1e-3,
    "short tons": 0.907185,   # EPA sometimes reports short tons
}

_TO_MWH = {"mwh": 1.0, "kwh": 1e-3, "gwh": 1e3, "twh": 1e6, "mmbtu": 0.293071}
_TO_M3 = {"m3": 1.0, "megalitres": 1e3, "ml": 1e3, "cubic metres": 1.0, "gallons": 0.00378541}
_SCALE = {"": 1.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9}


def to_tco2e(value: float, unit: str) -> float:
    u = unit.strip().lower()
    if u not in _TO_TCO2E:
        raise ValueError(f"unknown emissions unit {unit!r}")
    return float(value) * _TO_TCO2E[u]


def to_mwh(value: float, unit: str) -> float:
    u = unit.strip().lower()
    if u not in _TO_MWH:
        raise ValueError(f"unknown energy unit {unit!r}")
    return float(value) * _TO_MWH[u]


def to_m3(value: float, unit: str) -> float:
    u = unit.strip().lower()
    if u not in _TO_M3:
        raise ValueError(f"unknown volume unit {unit!r}")
    return float(value) * _TO_M3[u]


def to_usd(value: float, scale: str = "", currency: str = "USD") -> float:
    """Absolute dollars. Non-USD raises: every S&P 500 registrant reports in
    USD, so a foreign currency here means the extraction grabbed the wrong
    table, and silently converting would hide that."""
    if currency.upper() != "USD":
        raise ValueError(f"expected USD, got {currency!r} -- check the source table")
    s = scale.strip().lower()
    if s not in _SCALE:
        raise ValueError(f"unknown scale {scale!r}")
    return float(value) * _SCALE[s]


def to_pct(value: float, as_fraction: bool = False) -> float:
    """Canonical percent is 0-100, not 0-1. Mixing the two is the quietest
    possible way to make a score wrong by 100x."""
    v = float(value) * 100 if as_fraction else float(value)
    if not 0 <= v <= 100:
        raise ValueError(f"percent out of range: {v}")
    return v


def fiscal_year(period_end: str | date, *, cutover_month: int = 6) -> int:
    """Align a period end date to a comparable fiscal year.

    A January year-end belongs with the PREVIOUS calendar year's cohort
    (retailers' FY2024 ends Jan 2025). Without this, a quarter of the index is
    compared against the wrong peer year.
    """
    d = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end
    return d.year - 1 if d.month < cutover_month else d.year


def cagr(start: float, end: float, years: float) -> float | None:
    if years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / years) - 1
