"""Deterministic indicator extraction with conservative normalization."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedIndicator:
    type: str
    normalized_value: str


_PATTERNS: tuple[tuple[str, re.Pattern[str], callable], ...] = (
    ("ipv4", re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])"), lambda v: v),
    ("ipv6", re.compile(r"(?<![\w:])(?:[\da-f]{1,4}:){2,7}[\da-f]{1,4}(?![\w:])", re.I), lambda v: v.lower()),
    ("url", re.compile(r"\bhttps?://[^\s\"'<>]+", re.I), lambda v: v.lower().rstrip(".,)")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), lambda v: v.lower()),
    ("sha256", re.compile(r"\b[a-f0-9]{64}\b", re.I), lambda v: v.lower()),
    ("sha1", re.compile(r"\b[a-f0-9]{40}\b", re.I), lambda v: v.lower()),
    ("md5", re.compile(r"\b[a-f0-9]{32}\b", re.I), lambda v: v.lower()),
    ("domain", re.compile(r"(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?![\w.-])", re.I), lambda v: v.lower()),
)


def extract_indicators(content: str) -> list[ExtractedIndicator]:
    values: dict[tuple[str, str], ExtractedIndicator] = {}
    for indicator_type, pattern, normalize in _PATTERNS:
        for match in pattern.finditer(content):
            value = normalize(match.group(0))
            # Avoid treating a URL's host as an independent domain occurrence;
            # the URL itself preserves the strongest source assertion.
            if indicator_type == "domain" and (value.endswith(".log") or value.endswith(".json") or value.endswith(".csv")):
                continue
            values.setdefault((indicator_type, value), ExtractedIndicator(indicator_type, value))
    return list(values.values())
