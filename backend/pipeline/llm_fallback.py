"""
SmartLog AI pipeline — Stage 5: LLM fallback via the Anthropic Claude API.

Called only when regex and the ML head were both inconclusive AND the log is
DBSCAN noise (a genuine outsider). Sends a few-shot prompt and demands strict
JSON. Missing ANTHROPIC_API_KEY, import failure, JSON parse failure, API
error or timeout all degrade gracefully: the caller falls back to
category "Unknown" with low confidence. This stage must NEVER crash the app.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from config import ANTHROPIC_API_KEY

# Asked again in the prompt so the model cannot drift off the taxonomy.
VALID_CATEGORIES = [
    "Database Error", "API Failure", "Login Failure", "Payment Issue",
    "Security Alert", "Resource Usage", "Workflow Error", "User Action",
]
VALID_SEVERITIES = ["Critical", "High", "Medium", "Low"]

LLM_TIMEOUT_S = 10.0
LLM_MAX_TOKENS = 300

# Small few-shot pairs; keep answers terse so tokens stay predictable.
_FEWSHOT = (
    'Example 1:\nlog: "db pool exhausted, connection refused after 30 retries"\n'
    '{"category": "Database Error", "severity": "Critical", "explanation": "The database connection pool was exhausted and refused further connections.", "remediation": "Increase pool size or kill long-running transactions; check the slow-query log."}\n'
    'Example 2:\nlog: "payment gateway returned verification failed for order settlement"\n'
    '{"category": "Payment Issue", "severity": "High", "explanation": "The payment gateway rejected settlement verification for an order.", "remediation": "Reconcile the order with the gateway and retry verification."}\n'
    'Example 3:\nlog: "frontend sent an unrecognized action type the workflow state machine does not know"\n'
    '{"category": "Workflow Error", "severity": "Medium", "explanation": "An unrecognized workflow action reached the state machine.", "remediation": "Inspect the client build; re-run the workflow step."}\n'
)

_SYSTEM = (
    "You classify enterprise log lines for an incident-monitoring tool. "
    "Answer with STRICT JSON only — no markdown, no commentary. Schema: "
    '{"category": one of ' + json.dumps(VALID_CATEGORIES) + ", "
    '"severity": one of ' + json.dumps(VALID_SEVERITIES) + ", "
    '"explanation": one short sentence, "remediation": one short sentence}.'
)


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a possibly chatty model reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def classify_with_llm(raw_text: str, cleaned_text: str) -> Optional[dict]:
    """
    Returns {category, severity, explanation, remediation} or None.

    None means "degrade to Unknown" — key missing, SDK error, timeout,
    bad JSON or the model strayed outside the taxonomy.
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT_S)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=LLM_MAX_TOKENS,
            system=_SYSTEM,
            messages=[
                {"role": "user", "content": f"{_FEWSHOT}Now classify:\nlog: {raw_text[:600]}"},
            ],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        parsed = _extract_json(text)
        if not parsed or parsed.get("category") not in VALID_CATEGORIES:
            return None
        severity = parsed.get("severity")
        return {
            "category": parsed["category"],
            "severity": severity if severity in VALID_SEVERITIES else "Medium",
            "explanation": str(parsed.get("explanation", "")).strip() or "Classified by the LLM fallback stage.",
            "remediation": str(parsed.get("remediation", "")).strip(),
        }
    except Exception:  # noqa: BLE001 — every failure path must degrade, never crash
        return None
