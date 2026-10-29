"""
SmartLog AI pipeline — Stage 1: preprocessing.

Strips timestamps, IDs, IPs, hex blobs, bare numbers and symbol noise from a
log line, lowercases the result and collapses whitespace, leaving a short
"semantic" string the regex/ML stages can match on.
"""

import re

# Ordered substitutions: most specific first.
_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    # ISO8601 / syslog-style timestamps
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), " "),
    (re.compile(r"\b[a-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b"), " "),                     # Jan 12 03:14:15
    (re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?(?:\.\d+)?\b"), " "),                            # 12:34:56
    # IPv4 / IPv6
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), " "),
    (re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{0,4}\b", re.IGNORECASE), " "),
    # Hex blobs / hashes / ids
    (re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE), " "),
    (re.compile(r"\b(?:id|req(?:uest)?|user|txn|trace)[_-]?(?:id)?[:#]?\s*[0-9a-zA-Z-]{4,}\b",
                re.IGNORECASE), " "),
    # Bare numbers (including decimals with units like 98.7% or 1024ms)
    (re.compile(r"\b\d+(?:\.\d+)?\b"), " "),
    # Anything that is not a letter, apostrophe or hyphen
    (re.compile(r"[^a-z' ]"), " "),
]


def preprocess(text: str) -> str:
    """
    Clean one raw log line.

    Returns the lowercased, whitespace-normalized text with timestamps,
    identifiers, IPs, hex, numbers and symbols removed.
    """
    cleaned = text.lower()
    for pattern, replacement in _SUBSTITUTIONS:
        cleaned = pattern.sub(replacement, cleaned)
    # collapse whitespace left behind
    return re.sub(r"\s+", " ", cleaned).strip()
