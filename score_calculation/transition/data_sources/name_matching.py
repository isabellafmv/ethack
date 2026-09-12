"""Shared company-name normalization/matching used to join messy legal
names (SBTi export, EPA GHGRP parent-company file) onto the S&P 500 list.
"""
import difflib
import re

SUFFIXES = [
    "incorporated", "corporation", "company", "holdings", "holding",
    "group", "limited", "worldwide", "international", "inc", "corp",
    "co", "plc", "ltd", "llc", "na", "sa", "nv", "se", "ag", "the",
]


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\(class [^)]+\)", "", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)  # drop punctuation and stray artifacts (e.g. trailing "|")
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens).strip()


def fuzzy_match_is_safe(query: str, candidate: str) -> bool:
    """Guard against same-edit-distance, different-company collisions
    (e.g. "vertiv" vs "veritiv" are both ratio~0.92 but unrelated firms).
    Single-token names are only ever matched exactly (too risky to fuzz);
    multi-token names must agree on every token but the last.
    """
    query_tokens, candidate_tokens = query.split(), candidate.split()
    if len(query_tokens) == 1 or len(candidate_tokens) == 1:
        return query == candidate
    return query_tokens[:-1] == candidate_tokens[:-1]


def best_match(normalized_query: str, lookup: dict, candidate_names: list, cutoff: float = 0.92):
    """Return (matched_value, match_quality) from `lookup` (keyed by
    normalized name), trying an exact match first, then a guarded fuzzy one.
    """
    match = lookup.get(normalized_query)
    if match is not None:
        return match, "exact"

    close = difflib.get_close_matches(normalized_query, candidate_names, n=3, cutoff=cutoff)
    safe_close = [c for c in close if fuzzy_match_is_safe(normalized_query, c)]
    if safe_close:
        return lookup[safe_close[0]], "fuzzy"

    return None, None
