"""The rule, in one place: a quote is valid only if it is a character-for-
character substring of the source text.

Everything else in this file is about making that test survive HTML. A quote
pulled from a rendered filing will differ from the raw bytes by whitespace
runs, non-breaking spaces and smart quotes. Normalising BOTH sides for those
-- and nothing else -- keeps the test honest while not failing on typography.

What is deliberately NOT normalised: case, digits, punctuation that changes
meaning, or word order. If an agent paraphrased, this must fail.
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")

# Typographic characters that render identically but differ in bytes.
_LOOKALIKES = {
    " ": " ", " ": " ", " ": " ", "​": "",
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
    "…": "...",
}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _LOOKALIKES.items():
        text = text.replace(bad, good)
    return _WS.sub(" ", text).strip()


def verify(quote: str | None, source_text: str) -> bool:
    """True iff `quote` really appears in `source_text`."""
    if not quote or not quote.strip():
        return False
    return normalise(quote) in normalise(source_text)


MIN_QUOTE_CHARS = 20


def is_substantive(quote: str | None) -> bool:
    """A two-word quote verifies against almost anything and proves nothing."""
    return bool(quote) and len(normalise(quote)) >= MIN_QUOTE_CHARS


NEGATIONS = (
    "do not", "does not", "did not", "no ", "none", "not maintain",
    "have not", "has not", "without", "absent", "declined to",
)


def looks_negated(quote: str, window: int = 120) -> bool:
    """Cheap guard for the trap named in the register: 'we do not maintain a
    clawback policy' contains the keyword and means the opposite.

    This is a FLAG for review, not a decision. A boolean extraction whose quote
    trips this should be re-read before it is trusted.
    """
    head = normalise(quote).lower()[:window]
    return any(n in head for n in NEGATIONS)
