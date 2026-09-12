"""Column detection and value parsing for the SBTi export. HAND-WRITTEN.

The export's column names change between releases, so nothing here hard-codes a
single header. Each logical column is matched by a list of patterns against the
normalised header, and `detect()` reports what it found — so a release that
renames a column produces a loud mismatch rather than a silently empty field.
"""

from __future__ import annotations

import re

from ...common.columns import detect as _detect

COLUMNS = {
    "company":   ["company name", "company", "organisation", "organization", "name"],
    "country":   ["location", "country", "region", "iso"],
    "isin":      ["isin"],
    "lei":       ["lei"],
    "action":    ["action", "target or commitment"],
    # The real export is WIDE: one row per company, with a near-term column
    # group and a net-zero column group side by side. Detect them separately so
    # the choice between them is made on data, not on row order.
    "nt_status": ["near term target status", "near term status",
                  "short term target status", "near term target classification"],
    "nt_year":   ["near term target year"],
    "nt_scope":  ["near term scope", "near term target scope"],
    "nz_status": ["net zero target status", "net zero status",
                  "long term target status", "net zero committed"],
    "nz_year":   ["net zero target year", "net zero year"],
    # Fallbacks for a LONG-format export (one row per target).
    "target_type": ["target classification", "target type", "classification"],
    "target_year": ["target year", "year"],
    "base_year": ["base year", "baseline year"],
    "scope":     ["target scope", "scope"],
    "date":      ["date published", "date", "published"],
    "reduction": ["reduction", "ambition", "% reduction", "target ambition"],
    "language": ["full target language", "target language", "target wording"],
}


def detect(headers: list[str]) -> dict[str, str | None]:
    return _detect(headers, COLUMNS)


_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def year(value) -> int | None:
    if value is None:
        return None
    m = _YEAR.search(str(value))
    y = int(m.group(0)) if m else None
    # A "target year" outside this window is a parse error, not a target.
    return y if y and 1990 <= y <= 2100 else None


def percent(value) -> float | None:
    if value is None:
        return None
    m = _PCT.search(str(value))
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 <= v <= 100 else None


#: SBTi distinguishes a VALIDATED target from a mere commitment to set one.
#: Treating a commitment as a target is the single easiest way to flatter a
#: company here, so the two are kept apart explicitly.
VALIDATED = ("targets set", "target set", "targets", "near-term", "net-zero",
             "near term", "net zero", "validated")
COMMITTED = ("commitment", "committed")


def is_validated(action, target_type) -> bool:
    blob = f"{action or ''} {target_type or ''}".lower()
    if any(c in blob for c in COMMITTED) and not any(v in blob for v in VALIDATED):
        return False
    return any(v in blob for v in VALIDATED)


def target_type(action, target_type_col) -> str | None:
    blob = f"{action or ''} {target_type_col or ''}".lower()
    if "net-zero" in blob or "net zero" in blob:
        return "net-zero"
    if "near-term" in blob or "near term" in blob or "short term" in blob:
        return "near-term"
    if any(c in blob for c in COMMITTED):
        return "commitment"
    return None


def classify(nt_status, nt_year, nz_status, nz_year, action, target_type_col):
    """(type, target_year) for one company row.

    NEAR-TERM WINS when both exist, and that is a methodology choice, not a
    convenience. Net-zero targets are typically 2050, near-term typically 2030;
    feeding a 2050 horizon into the affordability ratio divides the same
    abatement bill over 26 years instead of 5, and almost everyone looks able to
    pay. The near-term target is also the one the company is on the hook for
    this decade. Conservative, and the honest reading.
    """
    nt_ok = is_validated(nt_status, None) or year(nt_year) is not None
    nz_ok = is_validated(nz_status, None) or year(nz_year) is not None
    if nt_ok:
        return "near-term", year(nt_year)
    if nz_ok:
        return "net-zero", year(nz_year)
    # Long-format export, or a company with only a commitment.
    t = target_type(action, target_type_col)
    return t, year(nt_year) or year(nz_year)


# --- target wording -------------------------------------------------------
# `full_target_language` carries SBTi's own sentence, e.g.
#   "Acme Corp commits to reduce absolute scope 1 and 2 GHG emissions 50% by
#    FY2030 from a FY2021 base year."
# Parsing it rather than taking a spreadsheet cell means every number arrives
# WITH THE SENTENCE IT CAME FROM, so it can be quote-verified — the only
# structured source in the project where that is possible.

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(&\"'])")
_REDUCTION = re.compile(
    r"reduce\s+(?P<absolute>absolute\s+)?(?P<scope>scope\s*[\d\s,and+&]*?)\s*"
    r"(?:GHG\s+)?emissions\s+(?:by\s+)?(?P<pct>\d{1,3}(?:\.\d+)?)\s*%",
    re.I)
_BY_YEAR = re.compile(r"\bby\s+(?:FY)?(?P<y>\d{4})", re.I)
_BASE_YEAR = re.compile(
    r"from\s+(?:a|an)?\s*(?:FY)?(?P<y>\d{4})\s+base[-\s]*year", re.I)
_INTENSITY = re.compile(r"\bper\s+(million|unit|tonne|ton|metric|sq|square|MWh|"
                        r"employee|value added|product)", re.I)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(str(text or "")) if s.strip()]


def parse_target_language(text: str) -> dict | None:
    """Pull reduction %, base year, target year and scope out of SBTi's wording.

    Returns the SENTENCE as `quote` so the value can be validated as a
    character-for-character substring of the source cell.

    Prefers an ABSOLUTE scope 1+2 target: that is what the affordability
    calculation needs. An intensity target ('per million DKK value added')
    describes a different quantity and cannot be multiplied by an abatement
    cost per tonne, so it is recorded but flagged.
    """
    best = None
    for s in sentences(text):
        m = _REDUCTION.search(s)
        if not m:
            continue
        scope = re.sub(r"\s+", " ", m.group("scope") or "").strip(" ,")
        scope = re.sub(r"^scopes?\s*", "", scope, flags=re.I).strip(" ,") or None
        intensity = bool(_INTENSITY.search(s))
        absolute = bool(m.group("absolute"))
        covers12 = bool(scope and re.search(r"\b1\b", scope)
                        and re.search(r"\b2\b", scope))
        # rank: absolute > not; scope 1+2 > other; non-intensity > intensity
        rank = (absolute, covers12, not intensity)
        cand = {
            "quote": s,
            "target_reduction_pct": float(m.group("pct")),
            "target_scope_coverage": scope,
            "target_year": int(_BY_YEAR.search(s).group("y")) if _BY_YEAR.search(s) else None,
            "target_baseline_year": int(_BASE_YEAR.search(s).group("y"))
                                    if _BASE_YEAR.search(s) else None,
            "is_intensity": intensity,
            "is_absolute": absolute,
            "_rank": rank,
        }
        if best is None or cand["_rank"] > best["_rank"]:
            best = cand
    if best:
        best.pop("_rank")
    return best
