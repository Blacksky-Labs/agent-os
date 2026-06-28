"""Deterministic signal extractors for the ingestion cell (the Sentiment Engine).

Pure functions. No I/O, no LLM, no entity knowledge. Regex extraction of
structured references from raw user text. These run on every turn for every
AgentOS entity — Skipper, Maurice, Judy, and the rest — and are entirely
domain-agnostic. Domain-specific interpretation is the optional LLM pass's job
(see cell.py), tuned per entity via manifest config.

See SPEC.md §5 (ingestion contract) and agentos-v1-spec.md §5 (Sentiment Engine).
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"\bhttps?://[^\s<>\")]+|\bwww\.[^\s<>\")]+", re.I)
MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{2,})")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,2}[\s.\-])?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
)
# $25k · $1,000 · $1.5M · $20-25k · $20 to 25k
MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kKmMbB]?"
    r"(?:\s?(?:-|–|to)\s?\$?\s?\d[\d,]*(?:\.\d+)?\s?[kKmMbB]?)?"
)
TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b", re.I)
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
QUARTER_RE = re.compile(r"\bQ[1-4]\b")
WEEKDAY_RE = re.compile(
    r"\b(?:Mon|Tue|Tues|Wed|Thur|Thu|Thurs|Fri|Sat|Sun)(?:day)?\b", re.I
)
MONTH_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)(?:[a-z]+)?\b"
)
RELATIVE_DATE_RE = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|"
    r"this (?:week|month|morning|afternoon|evening)|next (?:week|month))\b",
    re.I,
)
# Capitalized / CamelCase runs: "Jordan Tran", "AgentOS", "KNowGov".
PROPER_NOUN_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9]+)(?:\s+[A-Z][A-Za-z0-9]+)*\b")

# Single capitalized words that are almost never the entity we want.
_STOP_PROPER = {
    "i", "i'm", "i'll", "i've", "the", "a", "an", "this", "that", "these",
    "those", "my", "your", "our", "we", "you", "he", "she", "they", "it",
    "yes", "no", "ok", "okay", "hi", "hey", "hello", "good", "just", "so",
    "and", "but", "or", "if", "when", "what", "why", "how", "please", "thanks",
    "thank", "morning", "afternoon", "evening", "today", "tomorrow",
    # common sentence-initial verbs/words that aren't the entity we want
    "email", "call", "text", "send", "meet", "note", "let", "can", "could",
    "would", "should", "also", "here", "there", "sure", "need", "want", "make",
    "remember", "remind", "tell", "ask", "give", "add", "set", "check",
}


def _dedupe(seq) -> list[str]:
    """Order-preserving, case-insensitive dedupe."""
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        k = s.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out


def extract_emails(text: str) -> list[str]:
    return _dedupe(EMAIL_RE.findall(text))


def extract_urls(text: str) -> list[str]:
    return _dedupe(URL_RE.findall(text))


def extract_mentions(text: str) -> list[str]:
    return _dedupe("@" + m for m in MENTION_RE.findall(text))


def extract_phones(text: str) -> list[str]:
    return _dedupe(m.strip() for m in PHONE_RE.findall(text))


def extract_money(text: str) -> list[str]:
    return _dedupe(m.strip() for m in MONEY_RE.findall(text))


def extract_dates(text: str) -> list[str]:
    found: list[str] = []
    for rx in (ISO_DATE_RE, QUARTER_RE, RELATIVE_DATE_RE, WEEKDAY_RE, MONTH_RE, TIME_RE):
        found.extend(m if isinstance(m, str) else m[0] for m in rx.findall(text))
    return _dedupe(found)


def extract_proper_nouns(text: str) -> list[str]:
    """Capitalized/CamelCase candidate entities (people, projects, orgs)."""
    out: list[str] = []
    for cand in PROPER_NOUN_RE.findall(text):
        cand = cand.strip()
        if not cand:
            continue
        # quarters (Q1–Q4) are dates, not entities
        if QUARTER_RE.fullmatch(cand):
            continue
        # keep multi-word runs; for single tokens, drop common stopwords
        if " " not in cand and (cand.lower() in _STOP_PROPER or len(cand) < 2):
            continue
        out.append(cand)
    return _dedupe(out)


def extract_all(text: str) -> dict[str, list[str]]:
    """Run every deterministic extractor. Returns only non-empty channels,
    plus ``entities`` (proper-noun candidates). Pure; safe on any input."""
    text = text or ""
    result = {
        "emails": extract_emails(text),
        "phones": extract_phones(text),
        "urls": extract_urls(text),
        "mentions": extract_mentions(text),
        "money": extract_money(text),
        "dates": extract_dates(text),
        "entities": extract_proper_nouns(text),
    }
    return {k: v for k, v in result.items() if v}
