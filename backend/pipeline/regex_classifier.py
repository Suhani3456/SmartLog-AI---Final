"""
SmartLog AI pipeline — Stage 2: regex classifier.

A small hand-written rule table over the CLEANED text (from preprocess.py).
Each rule has an id (shown in the UI trace), a category and a set of keyword
phrases. If any phrase hits, the rule fires and the pipeline short-circuits
with high confidence — no ML call needed.

These rules stay usable in the real pipeline (Phase 3); they are the
"rule-based only" baseline in train.py too.
"""

import re
from dataclasses import dataclass
from typing import Optional

from pipeline.preprocess import preprocess


@dataclass(frozen=True)
class RegexRule:
    """One known-pattern rule."""

    rule_id: str
    category: str
    severity: str
    phrases: tuple[str, ...]          # any hit decides the rule


RULES: tuple[RegexRule, ...] = (
    RegexRule(
        rule_id="db_timeout_01",
        category="Database Error",
        severity="Critical",
        phrases=("connection timeout", "connection refused", "deadlock detected",
                 "deadlock", "database is locked", "ora-", "sqlstate", "query timeout",
                 "too many connections", "lock wait timeout", "disk full"),
    ),
    RegexRule(
        rule_id="api_5xx_01",
        category="API Failure",
        severity="High",
        phrases=("status", "internal server error", "gateway timeout",
                 "upstream error", "endpoint returned"),
    ),
    RegexRule(
        rule_id="api_upstream_02",
        category="API Failure",
        severity="High",
        phrases=("upstream timed out", "bad gateway", "service unavailable",
                 "failed to fetch", "request failed"),
    ),
    RegexRule(
        rule_id="auth_failed_01",
        category="Login Failure",
        severity="Medium",
        phrases=("login failed", "authentication failed", "invalid credentials",
                 "auth token invalid", "account locked", "invalid username or password",
                 "session expired"),
    ),
    RegexRule(
        rule_id="payment_decline_01",
        category="Payment Issue",
        severity="High",
        phrases=("transaction declined", "card declined", "refund failed",
                 "chargeback", "invoice", "settlement", "payment gateway",
                 "payment failed", "double charge"),
    ),
    RegexRule(
        rule_id="security_01",
        category="Security Alert",
        severity="Critical",
        phrases=("unauthorized", "brute force", "suspicious login", "acl",
                 "firewall", "permission denied", "security", "intrusion",
                 "malformed", "csrf", "sql injection"),
    ),
    RegexRule(
        rule_id="resource_01",
        category="Resource Usage",
        severity="Medium",
        phrases=("memory usage", "cpu usage", "disk usage", "heap", "garbage collection",
                 "out of memory", "load average", "swap", "throttled", "quota exceeded"),
    ),
    RegexRule(
        rule_id="workflow_01",
        category="Workflow Error",
        severity="Medium",
        phrases=("workflow", "job failed", "task failed", "state machine",
                 "retry limit", "orchestration", "pipeline aborted", "step skipped"),
    ),
    RegexRule(
        rule_id="user_action_01",
        category="User Action",
        severity="Low",
        phrases=("user logged in", "user logged out", "password changed",
                 "profile updated", "created a ticket", "exported report",
                 "performed action", "settings updated", "clicked"),
    ),
)

# Compiled once, lazily, at first use.
_COMPILED: dict[str, list[re.Pattern[str]]] = {}


def _compiled_phrases(rule: RegexRule) -> list[re.Pattern[str]]:
    """Compile a rule's phrases to word-boundary regexes, cached per rule id."""
    if rule.rule_id not in _COMPILED:
        _COMPILED[rule.rule_id] = [
            re.compile(r"\b" + re.escape(p) + r"\b") for p in rule.phrases
        ]
    return _COMPILED[rule.rule_id]


def match(raw_text: str, cleaned_text: Optional[str] = None) -> Optional[dict]:
    """
    Try every rule against the cleaned text.

    Returns None when no rule fires, otherwise:
      {rule_id, category, severity, confidence, matched_phrase}
    """
    cleaned = cleaned_text if cleaned_text is not None else preprocess(raw_text)
    for rule in RULES:
        for pattern in _compiled_phrases(rule):
            hit = pattern.search(cleaned)
            if hit:
                return {
                    "rule_id": rule.rule_id,
                    "category": rule.category,
                    "severity": rule.severity,
                    "confidence": 0.97,
                    "matched_phrase": hit.group(0),
                }
    return None
