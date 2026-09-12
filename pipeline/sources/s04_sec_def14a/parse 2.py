"""Phrase patterns and sentence extraction for DEF 14A proxies. HAND-WRITTEN.

Why patterns and not an LLM: the plan's own rule is "extract BOOLEANS with
verbatim quotes, not graded scores — graded scores over prose is where
hallucination lives". A phrase match returns the sentence it matched in, so the
quote is a substring BY CONSTRUCTION and validates every time. It costs
nothing, runs offline, and two runs give the same answer.

What it cannot do is read intent. Two guards for that:

  * NEGATION. "We do not maintain a clawback policy" contains the keyword and
    means the opposite. Every hit is checked and a negated one is recorded as
    False-with-quote, not True.
  * ABSENCE IS NOT FALSE for some fields and IS for others. A proxy that never
    mentions a climate committee almost certainly has none (these documents are
    exhaustive about committee structure), so absence reads False. A proxy we
    failed to parse reads not_disclosed. The difference is tracked.
"""

from __future__ import annotations

import re

# --- text extraction ------------------------------------------------------

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_BR = re.compile(r"</?(br|p|div|tr|li|h\d|td|table)[^>]*>", re.I)
_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\xa0]+")
_NL = re.compile(r"\n{3,}")


def html_to_text(html: str | bytes) -> str:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    t = _TAG.sub(" ", html)
    # Source newlines are LAYOUT, not sentence boundaries. HTML wraps a single
    # sentence across lines constantly, and splitting on those newlines cut
    # sentences in half so multi-clause patterns ("committee ... oversees ...
    # climate") could never match. Flatten first; only block-level tags then
    # introduce a real break.
    t = re.sub(r"\s+", " ", t)
    t = _BR.sub("\n", t)
    t = _ANY.sub(" ", t)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&#8217;", "'"),
                    ("&#8220;", '"'), ("&#8221;", '"'), ("&lt;", "<"),
                    ("&gt;", ">"), ("&#151;", "—"), ("&rsquo;", "'")):
        t = t.replace(ent, ch)
    t = _WS.sub(" ", t)
    return _NL.sub("\n\n", t)


_SPLIT = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z(])|\n+")


def sentences(text: str, max_len: int = 600) -> list[str]:
    out = []
    for s in _SPLIT.split(text):
        s = s.strip()
        if 20 <= len(s) <= max_len:
            out.append(s)
    return out


# --- negation -------------------------------------------------------------

_NEG = re.compile(
    r"\b(do(es)?\s+not|did\s+not|no\s+longer|have\s+not|has\s+not|"
    r"we\s+do\s+not|is\s+not|are\s+not|neither|never|without\s+a|"
    r"has\s+no\b|have\s+no\b|does\s+not\s+(currently\s+)?(maintain|have|"
    r"provide|tie|link))\b", re.I)


def negated(sentence: str) -> bool:
    """Cheap but targeted: the trap named in the register is
    'we do not maintain a clawback policy', which contains the keyword."""
    return bool(_NEG.search(sentence))


# --- boolean fields -------------------------------------------------------
# Each field: list of regexes. A sentence matching ANY pattern is a hit.
# `absence_is_false` says how to read a document with no hit at all.

BOOLEANS: dict[str, dict] = {
    # TIGHTENED after hand-checking. The first version counted "oversees our
    # corporate responsibility efforts, including sustainability initiatives"
    # as climate oversight. Sustainability and ESG are broader than climate,
    # and the field claims climate — so a CLIMATE word is now required, next to
    # an explicit oversight-by-a-committee construction.
    "has_climate_oversight_committee": {
        "patterns": [
            r"\bcommittee\b[^.]{0,90}\b(oversee\w*|oversight of|responsib\w+ for)"
            r"[^.]{0,90}\b(climate|greenhouse gas|GHG|decarboni\w+|net[- ]zero|"
            r"emissions? (target|reduction|goal))\b",
            r"\b(climate|greenhouse gas|GHG|decarboni\w+|net[- ]zero)\b"
            r"[^.]{0,70}\boversight\b[^.]{0,70}\bcommittee\b",
            r"\bcommittee\b[^.]{0,60}\bclimate[- ]related (risk|matter|issue)s?\b",
        ],
        "absence_is_false": True,
    },
    # DROPPED — see NOT_EXTRACTABLE below. Kept here only as documentation of
    # what was tried. It is not in EMITS and is never written.
    "_comp_tied_to_emissions_target__abandoned": {
        "patterns": [
            r"\b(annual|short[- ]term|long[- ]term|executive)\s+incentive"
            r"[^.]{0,110}\b(greenhouse gas|GHG|emissions?|carbon)\s*"
            r"(reduction|intensity|target|goal|metric|performance)?\b",
            r"\b(scorecard|performance metric|modifier|weighting|payout factor)\b"
            r"[^.]{0,90}\b(greenhouse gas|GHG|emissions?|carbon)\b",
            r"\b(greenhouse gas|GHG|emissions?|carbon)\s*"
            r"(reduction|intensity|target|goal)\b[^.]{0,90}"
            r"\b(annual incentive|bonus|STI|LTI|named executive officer|NEO|"
            r"compensation of our executive)\b",
        ],
        "exclude": [
            r"\b(supplier|customer|farmer|product|packaging|fleet|tenant)\b",
            r"\bwe (were )?responsible for\b", r"\bcalculat\w+ the\b",
            # A JOB TITLE, not a pay design: "Global Emissions Reduction Leader
            # ... at an annual total compensation of ..."
            r"\b(Leader|Officer|President|Head of|Director of)\b[^.]{0,40}"
            r"\b(effective|appointed|promoted|for his|for her)\b",
            r"\bfor (his|her) (position|role)\b",
            # A sentence LISTING the metrics, where the emissions word is
            # incidental: "core measures ... are EVA and Earnings Per Share".
            r"\b(measures?|metrics?)\s+(are|were)\s+(EVA|EPS|Earnings|revenue|"
            r"return on|operating income|free cash flow)\b",
        ],
        "proximity": 60,
        "absence_is_false": True,
    },
    "has_third_party_assurance": {
        "patterns": [
            r"\b(third[- ]party|independent|external)\b[^.]{0,60}"
            r"\b(assur\w+|verif\w+|attest\w+)\b[^.]{0,80}"
            r"\b(emission\w*|GHG|greenhouse gas|sustainab\w+|ESG)\b",
            r"\b(limited|reasonable)\s+assurance\b",
        ],
        "absence_is_false": True,
    },
    "emissions_boundary_stated": {
        "patterns": [
            r"\b(operational|equity|financial)\s+control\s+(approach|basis|method)",
            r"\bScope\s*1\b[^.]{0,60}\bScope\s*2\b",
            r"\bGHG Protocol\b",
        ],
        "absence_is_false": True,
    },
    "has_clawback_policy": {
        "patterns": [
            r"\bclawback\b", r"\brecoupment\b",
            r"\brecovery of (erroneously awarded|incentive)\b",
        ],
        "absence_is_false": True,
    },
    "has_psu_plan": {
        "patterns": [
            r"\bperformance[- ](share|stock)\s+units?\b", r"\bPSUs?\b",
            r"\bperformance[- ]based\s+restricted\s+stock\b",
        ],
        "absence_is_false": True,
    },
    "lead_independent_director": {
        "patterns": [r"\blead\s+independent\s+director\b",
                     r"\bindependent\s+lead\s+director\b"],
        "absence_is_false": True,
    },
}

#: Fields this source CANNOT extract by pattern, and why. Recorded so nobody
#: re-attempts it at hour 20 and ships the same false positives.
NOT_EXTRACTABLE = {
    "comp_tied_to_emissions_target":
        "Requires reading meaning, not matching words. Hand-checking every "
        "setting from loose to tightest gave near-100% false positives: job "
        "titles ('Global Emissions Reduction Leader ... at an annual total "
        "compensation'), supplier programmes, plain emissions disclosures, and "
        "sentences stating the metrics are EVA and EPS. Needs LLM extraction "
        "over the CD&A section with the quote-validation loop.",
}

#: Whether a document that never mentions the phrase counts as a real FALSE.
#: This is only sound where the detector has HIGH RECALL — a term of art that
#: any proxy using the concept would state. For low-recall concept detectors,
#: absence means "we did not find it", not "it is not there", and asserting
#: False would put a fabricated majority into the score.
HIGH_RECALL = {"has_clawback_policy", "has_psu_plan", "lead_independent_director"}

for name, _spec in BOOLEANS.items():
    _spec["absence_is_false"] = name in HIGH_RECALL

for _f in BOOLEANS.values():
    _f["compiled"] = [re.compile(p, re.I) for p in _f["patterns"]]
    _f["excluded"] = [re.compile(p, re.I) for p in _f.get("exclude", [])]


def find_boolean(text: str, field: str) -> tuple[bool | None, str | None, bool]:
    """(value, quote, negated). value None means nothing matched.

    Returns the FIRST non-negated hit if there is one, otherwise the first
    negated hit as an explicit False — 'we do not maintain a clawback policy'
    is a real answer, not a miss.
    """
    spec = BOOLEANS[field]
    first_neg = None
    for s in sentences(text):
        if any(rx.search(s) for rx in spec["excluded"]):
            continue          # context that makes the match mean something else
        for rx in spec["compiled"]:
            if rx.search(s):
                if negated(s):
                    first_neg = first_neg or s
                    break
                return True, s, False
    if first_neg:
        return False, first_neg, True
    return None, None, False


# --- numeric fields -------------------------------------------------------

# Proxies spell board numbers out far more often than they use digits
# ("Eight of our nine directors are independent"), so both forms are matched.
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
          "twenty": 20}
_N = r"(?:\d{1,2}|" + "|".join(_WORDS) + r")"

_BOARD = [
    # "all but one of our eleven directors" MUST be tried first: the general
    # pattern below also matches it, reading "one of our eleven" as 1 of 11 —
    # the exact inverse of what the sentence says.
    re.compile(rf"\ball\s+but\s+(?P<dep>{_N})\s+of\s+(?:our\s+)?"
               rf"(?P<tot>{_N})\s+(?:director|nominee)s?[^.]{{0,40}}"
               rf"\bindependent\b", re.I),
    re.compile(rf"(?P<ind>{_N})\s+of\s+(?:our\s+)?(?:then[- ]serving\s+)?"
               rf"(?P<tot>{_N})\s+(?:current\s+)?(?:director|nominee)s?"
               rf"[^.]{{0,40}}\bindependent\b", re.I),
    re.compile(rf"(?P<ind>{_N})\s+of\s+(?:our\s+)?(?P<tot>{_N})\s+"
               rf"directors?\s+are\s+independent", re.I),
]


def _n(v) -> int | None:
    if v is None:
        return None
    v = str(v).strip().lower()
    return _WORDS.get(v) or (int(v) if v.isdigit() else None)


_BOARD_REJECT = re.compile(
    r"\bin the (past|last)\b|\bover the (past|last)\b|\bwere elected\b|"
    r"\battend\w+\b|\bmeetings?\b|\bnominees? for election at\b", re.I)


def find_board(text: str) -> tuple[int | None, int | None, str | None]:
    """(independent_count, board_size, quote).

    Rejects sentences where the two numbers are counting something else —
    "In the past five years, five of our nine current directors were elected"
    matched the shape and meant nothing about independence.
    """
    for s in sentences(text):
        if _BOARD_REJECT.search(s):
            continue
        for rx in _BOARD:
            m = rx.search(s)
            if not m:
                continue
            g = m.groupdict()
            tot = _n(g.get("tot"))
            ind = _n(g.get("ind"))
            if ind is None and g.get("dep") is not None:
                d = _n(g["dep"])
                ind = tot - d if (tot is not None and d is not None) else None
            if tot and ind and 1 <= ind <= tot <= 30:
                return ind, tot, s
    return None, None, None


_ASSURANCE = re.compile(r"\b(limited|reasonable)\s+assurance\b", re.I)


def find_assurance_level(text: str) -> tuple[str | None, str | None]:
    for s in sentences(text):
        m = _ASSURANCE.search(s)
        if m:
            return m.group(1).lower(), s
    return None, None


_PERIOD = re.compile(r"\b(?P<n>one|two|three|four|five|\d)[- ]year\s+"
                     r"performance\s+(period|cycle)", re.I)
_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def find_performance_period(text: str) -> tuple[float | None, str | None]:
    for s in sentences(text):
        m = _PERIOD.search(s)
        if m:
            n = m.group("n").lower()
            v = _NUMS.get(n) or (int(n) if n.isdigit() else None)
            if v and 1 <= v <= 10:
                return float(v), s
    return None, None
