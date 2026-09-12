"""S02 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

Only risk_hitword_density and risk_first_factor_topic are built here -- both
rule-based over the actual Item 1A text, no agent call. energy_cost_usd,
clean_capex_usd, green_revenue_share_pct and target_year all need judgment
("the classification is OURS, not the company's" -- SOURCE.md) which means
reading MD&A prose and writing a quote-verified claim, i.e. agent-based
extraction (extracted_by="agent:..."). That is a materially bigger,
costlier task (an LLM call per candidate number per company) and is
deliberately NOT attempted in this pass -- see SOURCE.md before adding it
so the quote-verification and cost tradeoffs are made on purpose.

risk_first_factor_topic: 10-Ks conventionally group Item 1A under short
bolded category headers ("Macroeconomic and Industry Risks", "Legal and
Regulatory Risks", ...) before the individual risk statements. After
skipping the generic disclaimer boilerplate every filer opens with, the
first surviving paragraph -- heading or not -- is classified into a fixed
topic taxonomy by keyword match. This is "what comes first", the plan
doc's stated definition, without needing an LLM to summarise it.

risk_hitword_density: same HITWORDS as S03 (duplicated here on purpose --
importing from another source package is against the repo's own rule; keep
the two lists in sync by hand, they are declared as siblings in
common/fields.py). Unlike S03's crude hit/no-hit, this has the real text,
so it can do what the plan doc actually asked for: weight by POSITION
(earlier paragraph = higher weight) and by proximity to an intensifier
word in the same paragraph. Still no negation handling -- a hitword inside
"we do not expect a material weakness" scores the same as a genuine one;
name that limit in the pitch, same as S03.
"""

from __future__ import annotations

import argparse
import json
import re

from bs4 import BeautifulSoup

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

SOURCE = "S02"

#: Kept identical to s03_sec_fts.pull.HITWORDS by hand -- see module docstring.
HITWORDS = [
    "material weakness", "going concern", "goodwill impairment",
    "cybersecurity incident", "data breach", "product recall",
    "supply chain disruption", "regulatory investigation", "class action",
    "labor shortage", "geopolitical conflict", "interest rate volatility",
]
_INTENSIFIERS = ("significant", "material", "substantial", "severe")
_MAX_WEIGHT = 1.5  # paragraph 0 (weight 1.0) with an intensifier (x1.5)

#: First matching bucket wins, checked in this order -- order matters for
#: paragraphs that could plausibly fit more than one (e.g. a supply-chain
#: paragraph that also mentions "regulatory").
_TOPIC_KEYWORDS = [
    ("cybersecurity", ("cybersecurity", "cyber attack", "cyberattack",
                        "data breach", "information security")),
    ("supply_chain", ("supply chain", "suppliers", "sourcing", "manufacturing")),
    ("geopolitical", ("geopolitical", "tariff", "sanctions", "trade war",
                       "war ", "armed conflict")),
    ("macroeconomic", ("macroeconomic", "economic conditions", "inflation",
                        "interest rate", "recession", "currency")),
    ("regulatory", ("regulat", "legislat", "compliance", "government polic")),
    ("litigation", ("litigation", "lawsuit", "legal proceeding")),
    ("intellectual_property", ("intellectual property", "patent", "trademark",
                                "trade secret")),
    ("workforce", ("employee", "workforce", "labor", "talent", "personnel")),
    ("climate", ("climate", "environmental", "severe weather", "sustainab")),
    ("competition", ("competit", "market share")),
    ("financial", ("indebtedness", "credit rating", "liquidity", "capital markets")),
    ("product_quality", ("product quality", "defect", "recall")),
]

#: Paragraphs opening the section that are boilerplate disclaimer, not
#: content -- skipped when finding "the first risk factor".
_BOILERPLATE_MARKERS = (
    "following summarizes", "read in conjunction", "not exhaustive",
    "accurately predict", "beliefs and opinions", "forward-looking",
)


def _item_1a_paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    text = re.sub(r"[\xa0\s]*\n[\xa0\s]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)

    starts = [m.start() for m in
              re.finditer(r"item\s+1a\.?\s*risk\s*factors", text, re.I)]
    if not starts:
        return []
    start = starts[-1]  # last match skips the table-of-contents entry
    end_m = re.search(r"item\s+1b\.?\s*unresolved", text[start + 50:], re.I)
    end = start + 50 + end_m.start() if end_m else min(start + 60000, len(text))
    section = text[start:end]

    paras = [p.strip() for p in section.split("\n") if len(p.strip()) > 2]
    return paras[1:]  # drop the "Item 1A. Risk Factors" heading line itself


#: get_text() splits on every inline tag boundary, not real paragraphs, so
#: a page footer ("2025 Form 10-K") or a bare page number can land as its
#: own "paragraph" ahead of the real first risk-factor content. A window
#: of the first several substantive lines, not just the very first one, is
#: what keeps that from being misread as "no topic matched" -- see the
#: AbbVie case in the module's test notes: its first two survivors are a
#: generic "Risks Related to AbbVie's Business" heading and a footer, with
#: the real signal (patents) one line later.
_SCAN_WINDOW = 6
_JUNK_LINE = re.compile(r"^\d{4}\s+form\s+10-?k$|^page\s+\d+$|^\d+$", re.I)


def _first_factor_topic(paragraphs: list[str]) -> str | None:
    seen = 0
    for p in paragraphs:
        low = p.lower()
        if any(marker in low for marker in _BOILERPLATE_MARKERS):
            continue
        if _JUNK_LINE.match(p.strip()):
            continue
        seen += 1
        for topic, keywords in _TOPIC_KEYWORDS:
            if any(kw in low for kw in keywords):
                return topic
        if seen >= _SCAN_WINDOW:
            return "other"  # first several substantive lines matched no bucket
    return "other" if seen else None


def _hitword_density(paragraphs: list[str]) -> float | None:
    if not paragraphs:
        return None
    total = 0.0
    for word in HITWORDS:
        best = 0.0
        for i, p in enumerate(paragraphs):
            low = p.lower()
            if word not in low:
                continue
            weight = 1.0 / (1 + i)
            if any(intensifier in low for intensifier in _INTENSIFIERS):
                weight *= 1.5
            best = max(best, weight)
        total += best
    return total / (_MAX_WEIGHT * len(HITWORDS))


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raw = cache.get_raw(SOURCE, ticker, ".json")
            if raw is None:
                continue

            payload = json.loads(raw)
            filing = payload.get("filing")
            html = payload.get("html")

            if filing is None or html is None:
                for field in ("risk_hitword_density", "risk_first_factor_topic"):
                    w.write(Observation(
                        ticker=ticker, field=field, value=None, unit=None,
                        fiscal_year=0, period_end=None, quote=None,
                        source=SOURCE, source_url="https://www.sec.gov/cgi-bin/browse-edgar",
                        source_section="Item 1A", extracted_by="rule:item_1a_parse",
                        status=Status.NOT_DISCLOSED,
                    ))
                continue

            paragraphs = _item_1a_paragraphs(html)
            fiscal_year = int((filing.get("report_date") or filing.get("filing_date"))[:4])
            acc = filing["accession"]
            source_url = (f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/"
                          f"{acc.replace('-', '')}/{acc}-index.html")

            if not paragraphs:
                for field in ("risk_hitword_density", "risk_first_factor_topic"):
                    w.write(Observation(
                        ticker=ticker, field=field, value=None, unit=None,
                        fiscal_year=fiscal_year, period_end=filing.get("report_date"),
                        quote=None, source=SOURCE, source_url=source_url,
                        source_section="Item 1A", extracted_by="rule:item_1a_parse",
                        status=Status.NOT_DISCLOSED,
                    ))
                continue

            density = _hitword_density(paragraphs)
            w.write(Observation(
                ticker=ticker, field="risk_hitword_density", value=density, unit="index",
                fiscal_year=fiscal_year, period_end=filing.get("report_date"), quote=None,
                source=SOURCE, source_url=source_url,
                source_section=f"Item 1A:{acc}",
                extracted_by="rule:item_1a_position_weighted_hitwords",
                status=Status.STRUCTURAL,
            ))

            topic = _first_factor_topic(paragraphs)
            if topic is None:
                w.write(Observation(
                    ticker=ticker, field="risk_first_factor_topic", value=None, unit=None,
                    fiscal_year=fiscal_year, period_end=filing.get("report_date"),
                    quote=None, source=SOURCE, source_url=source_url,
                    source_section="Item 1A", extracted_by="rule:item_1a_first_paragraph",
                    status=Status.NOT_DISCLOSED,
                ))
            else:
                w.write(Observation(
                    ticker=ticker, field="risk_first_factor_topic", value=topic, unit=None,
                    fiscal_year=fiscal_year, period_end=filing.get("report_date"),
                    quote=None, source=SOURCE, source_url=source_url,
                    source_section=f"Item 1A:{acc}",
                    extracted_by="rule:item_1a_first_paragraph",
                    status=Status.STRUCTURAL,
                ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S02 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
